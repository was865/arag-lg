"""入庫パイプライン `run_ingest`（specs/003-ingestion/design.md §3.1、R13・R24〜R26）。

依存はすべて IngestDeps で注入する（テストは偽の解析器・埋め込み・索引を渡す）。
LangGraph の StateGraph は使わない（直線的な段階処理で、分岐・中断再開が不要なため。design §1）。
"""

import asyncio
import json
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.types.doc.document import DoclingDocument
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.db.models import Chunk, Content, Document, IngestJob, Section
from arag.ingest import queue
from arag.ingest.chunking import CHUNKER_VERSION, ChunkDraft, ChunkingResult, chunk_document, page_unit_for
from arag.ingest.contextualize import Contextualizer, HeadingContextualizer, Usage
from arag.ingest.embedder import Embedder, EmbedError
from arag.ingest.events import NoopPublisher, Publisher
from arag.ingest.figures import FigureDescriber, describe_figures
from arag.ingest.index import IndexPoint, live_refs
from arag.ingest.parser import DoclingServeParser, ParseError, ParseResult, PlainTextParser, select_parser
from arag.ingest.sparse import SPARSE_VERSION, SparseEncoder
from arag.logging import get_logger
from arag.storage import Storage, content_prefix

log = get_logger("arag.ingest.pipeline")


class Index(Protocol):
    async def ensure_collection(self, dim: int) -> None: ...
    async def upsert(self, points: list[IndexPoint], batch: int = 128) -> None: ...
    async def delete_content(self, content_hash: str) -> None: ...


@dataclass
class IngestDeps:
    sessionmaker: async_sessionmaker[AsyncSession]
    storage: Storage
    tokenizer: BaseTokenizer
    embedder: Embedder
    index: Index
    plain: PlainTextParser = field(default_factory=PlainTextParser)
    docling: DoclingServeParser | None = None
    contextualizer: Contextualizer = field(default_factory=HeadingContextualizer)
    describer: FigureDescriber | None = None
    sparse_factory: Callable[[], SparseEncoder] = SparseEncoder
    publisher: Publisher = field(default_factory=NoopPublisher)
    section_max_tokens: int = 2000
    section_level: int = 2
    max_retries: int = 3


class Cancelled(Exception):
    pass


class _Run:
    def __init__(self, job_id: uuid.UUID, deps: IngestDeps) -> None:
        self.job_id = job_id
        self.deps = deps
        self.extra: dict[str, Any] = {}

    async def progress(self, stage: str, progress: int, detail: str, *, status: str = "running") -> None:
        async with self.deps.sessionmaker() as s:
            await s.execute(
                update(IngestJob)
                .where(IngestJob.id == self.job_id)
                .values(stage=stage, progress=progress, stage_detail=detail, status=status)
            )
            await s.commit()
        await self.publish(stage=stage, progress=progress, stage_detail=detail, status=status)

    async def publish(self, **event: Any) -> None:
        try:
            await self.deps.publisher.publish(
                str(self.job_id), {"job_id": str(self.job_id), **self.extra, **event}
            )
        except Exception as e:  # 通知の失敗で入庫を止めない（DB が正）
            log.warning("publish_failed", error=f"{type(e).__name__}: {e}")

    async def check_cancel(self) -> None:
        async with self.deps.sessionmaker() as s:
            if await queue.is_cancel_requested(s, self.job_id):
                raise Cancelled()


async def _cleanup(session: AsyncSession, index: Index, content_hash: str) -> None:
    """前回の途中成果を消す（冪等な再実行。R25）。"""
    await index.delete_content(content_hash)
    await session.execute(delete(Chunk).where(Chunk.content_hash == content_hash))
    await session.execute(delete(Section).where(Section.content_hash == content_hash))


async def _title(session: AsyncSession, content_hash: str) -> str:
    name = await session.scalar(
        select(Document.filename)
        .where(Document.content_hash == content_hash)
        .order_by(Document.created_at)
        .limit(1)
    )
    return Path(name).stem if name else "文書"


async def _load_saved(storage: Storage, prefix: str) -> ParseResult | None:
    key = f"{prefix}/docling.json"
    if not await storage.exists(key):
        return None
    doc = DoclingDocument.model_validate_json(await storage.read(key))
    assets: dict[str, bytes] = {}
    for pic in doc.pictures:
        uri = str(pic.image.uri) if pic.image else ""
        if uri.startswith("assets/") and await storage.exists(f"{prefix}/{uri}"):
            assets[uri.removeprefix("assets/")] = await storage.read(f"{prefix}/{uri}")
    md = (
        (await storage.read(f"{prefix}/rendered.md")).decode()
        if await storage.exists(f"{prefix}/rendered.md")
        else ""
    )
    return ParseResult(doc=doc, markdown=md, page_count=None, parser="saved", assets=assets)


async def _parse(run: _Run, content: Content, deps: IngestDeps) -> ParseResult:
    prefix = content_prefix(content.content_hash)
    parser = select_parser(content.ext, deps.plain, deps.docling)
    parser_name: str = getattr(parser, "name", "unknown")
    if content.parser == parser_name:
        saved = await _load_saved(deps.storage, prefix)
        if saved is not None:  # 解析器の版が同じなら再解析しない（design §3.1）
            saved.page_count = content.page_count
            saved.parser = parser_name
            return saved

    async def on_pages(done: int, total: int) -> None:
        await run.progress("parsing", 5 + int(30 * done / max(total, 1)), f"解析中（{done}/{total} ページ）")

    original = f"{prefix}/original.{content.ext}"
    local = deps.storage.local_path(original)
    if local is None or not local.exists():
        raise ParseError("原本ファイルが見つかりません", f"missing {original}", retryable=False)
    result = await parser.parse(local, f"{content.content_hash}.{content.ext}", content.ext, on_pages)
    await deps.storage.put(
        f"{prefix}/docling.json", json.dumps(result.doc.export_to_dict(), ensure_ascii=False).encode()
    )
    await deps.storage.put(f"{prefix}/rendered.md", result.markdown.encode())
    for name, data in result.assets.items():
        await deps.storage.put(f"{prefix}/assets/{name}", data)
    return result


async def run_ingest(job_id: uuid.UUID, deps: IngestDeps) -> str:
    """1 ジョブを実行し、最終 status（ready / queued(再試行) / error / cancelled）を返す。"""
    run = _Run(job_id, deps)
    async with deps.sessionmaker() as s:
        job = await s.get(IngestJob, job_id)
        if job is None:
            return "missing"
        content = await s.get(Content, job.content_hash)
        assert content is not None
        content.status = "running"
        await s.commit()
    content_hash = content.content_hash
    try:
        # ---- parsing
        await run.progress("parsing", 5, "解析を開始しました")
        async with deps.sessionmaker() as s:
            await _cleanup(s, deps.index, content_hash)
            await s.commit()
            title = await _title(s, content_hash)
        parsed = await _parse(run, content, deps)
        if parsed.page_count:
            run.extra["page_count"] = parsed.page_count
        await run.check_cancel()

        # ---- chunking
        await run.progress("chunking", 40, "チャンクに分割しています")
        chunked: ChunkingResult = await asyncio.to_thread(
            chunk_document,
            parsed.doc,
            deps.tokenizer,
            section_max_tokens=deps.section_max_tokens,
            section_level=deps.section_level,
            page_unit=page_unit_for(content.ext),
        )
        await run.check_cancel()

        # ---- contextualizing（図の説明 → 文脈付与）
        await run.progress("contextualizing", 45, "図と文脈を整理しています")
        fig_usage = Usage()
        figures = await describe_figures(
            parsed.doc,
            parsed.assets,
            chunked.sections,
            chunked.chunks,
            deps.describer,
            deps.tokenizer.count_tokens,
            fig_usage,
        )
        chunks: list[ChunkDraft] = _merge_figures(chunked.chunks, figures)
        run.extra["chunk_count"] = len(chunks)

        async def on_ctx(done: int, total: int) -> None:
            if done == total or done % 10 == 0:
                await run.progress(
                    "contextualizing", 45 + int(25 * done / max(total, 1)), f"文脈付与中（{done}/{total}）"
                )

        ctx = await deps.contextualizer.contextualize(title, chunked.sections, chunks, on_ctx)
        await run.check_cancel()

        # ---- embedding
        await run.progress("embedding", 75, "ベクトル化しています")
        bodies = [f"{c}\n\n{ch.text}" if c else ch.text for c, ch in zip(ctx.contexts, chunks, strict=True)]
        dense = await deps.embedder.embed(bodies)
        encoder = deps.sparse_factory()
        sparse = await asyncio.to_thread(lambda: [encoder.encode_document(b) for b in bodies])
        await run.progress("embedding", 90, "ベクトル化が完了しました")
        await run.check_cancel()

        # ---- indexing
        await run.progress("indexing", 95, "索引に登録しています")
        await deps.index.ensure_collection(len(dense[0]) if dense else await deps.embedder.dimension())
        section_ids = [uuid.uuid4() for _ in chunked.sections]
        chunk_ids = [uuid.uuid4() for _ in chunks]
        async with deps.sessionmaker() as s:
            doc_ids, kb_ids = await live_refs(s, content_hash)
            s.add_all(
                Section(
                    id=section_ids[sec.ordinal],
                    content_hash=content_hash,
                    ordinal=sec.ordinal,
                    heading_path=sec.heading_path,
                    level=sec.level,
                    page_start=sec.page_start,
                    page_end=sec.page_end,
                    text=sec.text,
                    token_len=sec.token_len,
                )
                for sec in chunked.sections
            )
            await s.flush()
            s.add_all(
                Chunk(
                    id=chunk_ids[i],
                    content_hash=content_hash,
                    section_id=section_ids[ch.section_ordinal],
                    ordinal=ch.ordinal,
                    block_type=ch.block_type,
                    heading_path=ch.heading_path,
                    page_start=ch.page_start,
                    page_end=ch.page_end,
                    text=ch.text,
                    context=ctx.contexts[i],
                    context_source=ctx.sources[i],
                    token_len=ch.token_len,
                    boxes=ch.boxes,
                )
                for i, ch in enumerate(chunks)
            )
            await deps.index.upsert(
                [
                    IndexPoint(
                        id=chunk_ids[i],
                        dense=dense[i],
                        sparse=sparse[i],
                        payload={
                            "content_hash": content_hash,
                            "section_id": str(section_ids[ch.section_ordinal]),
                            "document_ids": doc_ids,
                            "kb_ids": kb_ids,
                            "block_type": ch.block_type,
                            "page_start": ch.page_start,
                            "heading_path": ch.heading_path,
                        },
                    )
                    for i, ch in enumerate(chunks)
                ]
            )
            # ---- ready
            usage = {
                "contextualize": ctx.usage.as_dict(),
                "context_model": ctx.model,
                "figures": fig_usage.as_dict(),
            }
            await s.execute(
                update(Content)
                .where(Content.content_hash == content_hash)
                .values(
                    status="ready",
                    error=None,
                    page_count=parsed.page_count or content.page_count,
                    parser=getattr(select_parser(content.ext, deps.plain, deps.docling), "name", None),
                    chunker_version=CHUNKER_VERSION,
                    embed_model=deps.embedder.model,
                    sparse_version=SPARSE_VERSION,
                    indexed_at=text("now()"),
                )
            )
            await s.execute(
                update(IngestJob)
                .where(IngestJob.id == job_id)
                .values(
                    status="ready",
                    stage="ready",
                    progress=100,
                    stage_detail="完了",
                    error=None,
                    usage=usage,
                    locked_by=None,
                    finished_at=text("now()"),
                )
            )
            await s.commit()
        await run.publish(stage="ready", progress=100, stage_detail="完了", status="ready")
        log.info(
            "ingest_ready", content_hash=content_hash, chunks=len(chunks), sections=len(chunked.sections)
        )
        return "ready"

    except Cancelled:
        async with deps.sessionmaker() as s:
            await _cleanup(s, deps.index, content_hash)
            await s.execute(
                update(IngestJob)
                .where(IngestJob.id == job_id)
                .values(
                    status="cancelled",
                    stage_detail="取り消しました",
                    locked_by=None,
                    finished_at=text("now()"),
                )
            )
            await s.execute(
                update(Content).where(Content.content_hash == content_hash).values(status="cancelled")
            )
            await s.commit()
        await run.publish(status="cancelled", stage_detail="取り消しました")
        return "cancelled"
    except Exception as e:
        user_message, retryable = _classify(e)
        detail = "".join(traceback.format_exception(e))
        log.warning(
            "ingest_failed", content_hash=content_hash, error=f"{type(e).__name__}: {e}", retryable=retryable
        )
        async with deps.sessionmaker() as s:
            status = await queue.record_failure(
                s,
                job_id,
                user_message=user_message,
                detail=detail,
                retryable=retryable,
                max_retries=deps.max_retries,
            )
        await run.publish(
            status=status,
            error=user_message if status == "error" else None,
            stage_detail=("エラー" if status == "error" else "再試行待ち"),
        )
        return status


def _merge_figures(chunks: list[ChunkDraft], figures: list[ChunkDraft]) -> list[ChunkDraft]:
    """図チャンクを所属セクションの末尾に差し込み、ordinal を振り直す。"""
    if not figures:
        return chunks
    out: list[ChunkDraft] = []
    by_section: dict[int, list[ChunkDraft]] = {}
    for f in figures:
        by_section.setdefault(f.section_ordinal, []).append(f)
    for i, c in enumerate(chunks):
        out.append(c)
        last_of_section = i + 1 == len(chunks) or chunks[i + 1].section_ordinal != c.section_ordinal
        if last_of_section:
            out.extend(by_section.pop(c.section_ordinal, []))
    for rest in by_section.values():
        out.extend(rest)
    for n, c in enumerate(out):
        c.ordinal = n
    return out


def _classify(e: Exception) -> tuple[str, bool]:
    if isinstance(e, ParseError):
        return e.user_message, e.retryable
    if isinstance(e, EmbedError):
        return "ベクトル化サービスでエラーが発生しました", True
    return "入庫中にエラーが発生しました", True
