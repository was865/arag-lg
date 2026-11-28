"""文脈付与モデルの比較（所要時間・失敗率・出力の並べ表示）。DB は書き換えない。

uv run python -m arag.eval.ctxbench --suite agentic_rag_demo beir_scifact jqara --docs 10 \\
    --model openai:gemma4-12b --base-url http://100.118.110.25:8093/v1 \\
    --kwargs '{"temperature": 0, "extra_body": {"chat_template_kwargs": {"enable_thinking": false}}}' \\
    --out ../eval/.reports/ctxbench/gemma4-12b.yaml

既存の文脈（context_source = llm のもの）は「基準」として並べる。
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.db.engine import make_engine, make_sessionmaker
from arag.db.models import Chunk, Document, Section
from arag.eval.__main__ import find_kb, kb_suite_of
from arag.ingest.chunking import ChunkDraft, SectionDraft
from arag.ingest.contextualize import LlmContextualizer
from arag.llm import chat_model
from arag.settings import Settings


async def _sample(session: AsyncSession, kb: str, n: int) -> list[tuple[str, str]]:
    """KB の文書から内容ハッシュ順に等間隔で n 件（再現できるように）。"""
    rows = (
        await session.execute(
            select(Document.filename, Document.content_hash)
            .where(Document.kb_id == kb, Document.deleted_at.is_(None))
            .order_by(Document.content_hash)
        )
    ).all()
    step = max(1, len(rows) // n)
    return [(r[0], r[1]) for r in rows[::step][:n]]


async def _load(session: AsyncSession, h: str) -> tuple[list[SectionDraft], list[ChunkDraft], list[Chunk]]:
    secs = list(
        await session.scalars(select(Section).where(Section.content_hash == h).order_by(Section.ordinal))
    )
    chunks = list(await session.scalars(select(Chunk).where(Chunk.content_hash == h).order_by(Chunk.ordinal)))
    ordinal = {s.id: s.ordinal for s in secs}
    sd = [
        SectionDraft(s.ordinal, s.heading_path, s.level, s.page_start, s.page_end, s.text, s.token_len)
        for s in secs
    ]
    cd = [
        ChunkDraft(
            c.ordinal,
            ordinal[c.section_id],
            c.block_type,  # type: ignore[arg-type]
            c.heading_path,
            c.page_start,
            c.page_end,
            c.text,
            c.token_len,
        )
        for c in chunks
    ]
    return sd, cd, chunks


async def main_async(args: argparse.Namespace) -> int:
    settings = Settings()
    model = chat_model(args.model, base_url=args.base_url, kwargs=json.loads(args.kwargs))
    ctx = LlmContextualizer(
        model,
        model_name=args.model,
        concurrency=args.concurrency,
        max_document_tokens=args.max_doc_tokens,
    )
    engine = make_engine(settings.database_url)
    items: list[dict[str, Any]] = []
    summary: dict[str, Any] = {"model": args.model, "concurrency": args.concurrency, "suites": {}}
    try:
        async with make_sessionmaker(engine)() as s:
            for suite in args.suite:
                kb = await find_kb(settings, kb_suite_of(suite))
                if kb is None:
                    raise SystemExit(f"KB がありません: {suite}")
                docs = await _sample(s, kb, args.docs)
                loaded = [(name, *(await _load(s, h))) for name, h in docs]
                t0 = time.perf_counter()
                # 文書単位で並列（入庫ワーカーの並列に相当）。文書内は contextualizer の並列
                results = await asyncio.gather(
                    *(ctx.contextualize(Path(name).stem, sd, cd) for name, sd, cd, _ in loaded)
                )
                elapsed = time.perf_counter() - t0
                n_chunks = sum(len(cd) for _, _, cd, _ in loaded)
                failures = sum(r.usage.failures for r in results)
                out_tokens = sum(r.usage.output_tokens for r in results)
                summary["suites"][suite] = {
                    "docs": len(loaded),
                    "chunks": n_chunks,
                    "failures": failures,
                    "seconds": round(elapsed, 1),
                    "chunks_per_sec": round(n_chunks / elapsed, 2) if elapsed else None,
                    "input_tokens": sum(r.usage.input_tokens for r in results),
                    "output_tokens": out_tokens,
                }
                print(f"{suite}: {json.dumps(summary['suites'][suite], ensure_ascii=False)}")
                for (name, _, cd, rows), r in zip(loaded, results, strict=True):
                    for c, row, new, src in zip(cd, rows, r.contexts, r.sources, strict=True):
                        items.append(
                            {
                                "suite": suite,
                                "document": name,
                                "ordinal": c.ordinal,
                                "chunk": c.text[:300],
                                "baseline": row.context if row.context_source == "llm" else None,
                                "candidate": new if src == "llm" else None,
                            }
                        )
    finally:
        await engine.dispose()
    dest = Path(args.out)
    await asyncio.to_thread(dest.parent.mkdir, parents=True, exist_ok=True)
    dump = yaml.safe_dump(
        {"summary": summary, "items": items}, allow_unicode=True, sort_keys=False, width=200
    )
    await asyncio.to_thread(dest.write_text, dump, encoding="utf-8")
    print(f"→ {dest}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="arag.eval.ctxbench")
    p.add_argument("--suite", nargs="+", required=True)
    p.add_argument("--docs", type=int, default=10, help="題集ごとの文書数")
    p.add_argument("--model", required=True)
    p.add_argument("--base-url", default="")
    p.add_argument("--kwargs", default="{}")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--max-doc-tokens", type=int, default=60_000)
    p.add_argument("--out", required=True)
    return asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
