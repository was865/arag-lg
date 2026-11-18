"""運用コマンド（R41・E1）。

python -m arag.cli reindex [--all | --content-hash H ... | --heading-context] [--dry-run]
python -m arag.cli ingest-dir DIR --kb KB_ID [--api URL] [--user ID --role admin]
python -m arag.cli gc [--retention-days N]
python -m arag.cli sync-payload
python -m arag.cli reparse-report [--content-hash H ...]
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from qdrant_client import AsyncQdrantClient
from sqlalchemy import or_, select

from arag.db.engine import make_engine, make_sessionmaker
from arag.db.models import Chunk, Content, IngestJob
from arag.devapi import DEV_API_URL, check_dev_api
from arag.ingest import queue
from arag.ingest.chunking import CHUNKER_VERSION
from arag.ingest.gc import run_gc
from arag.ingest.index import QdrantIndex, QdrantPayloadSync
from arag.ingest.report import build_report, load_report_dict, save_report
from arag.ingest.sparse import SPARSE_VERSION
from arag.kb.uploads import SUPPORTED
from arag.settings import Settings
from arag.storage import LocalStorage, content_prefix


async def reindex(
    settings: Settings, *, all_: bool, hashes: list[str], dry_run: bool, heading_context: bool = False
) -> int:
    """版の変わった内容を再投入する。保存済み docling.json を使うので再解析はしない。

    heading_context=True のときは、LLM の文脈が付かず見出しだけの子チャンクを持つ内容を対象にする
    （文脈付与モデルの障害・残高切れの後で付け直す）。
    """
    engine = make_engine(settings.database_url)
    sm = make_sessionmaker(engine)
    try:
        async with sm() as s:
            q = select(Content).where(Content.status.in_(["ready", "error"]))
            if hashes:
                q = q.where(Content.content_hash.in_(hashes))
            elif heading_context:
                q = q.where(
                    Content.content_hash.in_(
                        select(Chunk.content_hash).where(Chunk.context_source == "heading").distinct()
                    )
                )
            elif not all_:
                q = q.where(
                    or_(
                        Content.chunker_version.is_distinct_from(CHUNKER_VERSION),
                        Content.embed_model.is_distinct_from(settings.embed_model),
                        Content.sparse_version.is_distinct_from(SPARSE_VERSION),
                    )
                )
            targets = list(await s.scalars(q))
            print(f"対象: {len(targets)} 件")
            if dry_run:
                for c in targets:
                    print(
                        f"  {c.content_hash}  chunker={c.chunker_version}"
                        f" embed={c.embed_model} sparse={c.sparse_version}"
                    )
                return 0
            for c in targets:
                job = await s.scalar(
                    select(IngestJob)
                    .where(IngestJob.content_hash == c.content_hash)
                    .order_by(IngestJob.created_at.desc())
                    .limit(1)
                )
                if job is None:
                    await queue.enqueue(s, c.content_hash)
                elif job.status in ("queued", "running"):
                    continue
                else:
                    await queue.reset_for_retry(s, job)
            await s.commit()
            print("再投入しました（ワーカーが処理します）")
            return 0
    finally:
        await engine.dispose()


async def reparse_report(settings: Settings, *, hashes: list[str]) -> int:
    """保存済みの docling.json と DB のチャンクから解析の記録を作り直す（specs/030 R8）。"""
    from docling_core.types.doc.document import DoclingDocument

    engine = make_engine(settings.database_url)
    sm = make_sessionmaker(engine)
    storage = LocalStorage(settings.storage_dir)
    done = skipped = 0
    try:
        async with sm() as s:
            q = select(Content).where(Content.status == "ready")
            if hashes:
                q = q.where(Content.content_hash.in_(hashes))
            for c in list(await s.scalars(q)):
                prefix = content_prefix(c.content_hash)
                key = f"{prefix}/docling.json"
                if not await storage.exists(key):
                    skipped += 1
                    continue
                doc = DoclingDocument.model_validate_json(await storage.read(key))
                chunks = list(
                    await s.scalars(
                        select(Chunk).where(Chunk.content_hash == c.content_hash).order_by(Chunk.ordinal)
                    )
                )
                previous = await load_report_dict(storage, prefix)
                assets: set[str] = set()
                for p in doc.pictures:
                    uri = str(p.image.uri) if p.image else ""
                    if uri.startswith("assets/") and await storage.exists(f"{prefix}/{uri}"):
                        assets.add(uri.removeprefix("assets/"))
                report = build_report(
                    doc,
                    chunks,
                    parser=c.parser or "unknown",
                    docling=previous.get("docling") if previous else None,
                    asset_names=assets,
                    page_count=c.page_count,
                    check_bbox=c.ext.lower() == "pdf",
                )
                await save_report(storage, prefix, report)
                c.parse_warnings = report.warn_count
                done += 1
            await s.commit()
        print(f"作り直しました: {done} 件（docling.json が無く飛ばした: {skipped} 件）")
        return 0
    finally:
        await engine.dispose()


def _list_files(directory: Path) -> list[Path]:
    return sorted(
        p for p in directory.rglob("*") if p.is_file() and p.suffix.lower().lstrip(".") in SUPPORTED
    )


SSE_IDS_PER_STREAM = 100  # URL の長さを抑える


async def ingest_dir(
    directory: Path,
    *,
    api: str,
    kb: str,
    user: str,
    role: str,
    batch: int,
    timeout_sec: float,
    only: set[str] | None = None,
    quiet: bool = False,
) -> int:
    files = await asyncio.to_thread(_list_files, directory)
    if only is not None:
        files = [p for p in files if p.name in only]
    if not files:
        print("対象ファイルがありません", file=sys.stderr)
        return 1
    headers = {"X-Dev-User-Id": user, "X-Dev-Role": role}
    started = time.monotonic()
    jobs: dict[str, str] = {}
    async with httpx.AsyncClient(base_url=api.rstrip("/"), headers=headers, timeout=600) as client:
        await check_dev_api(client)
        for i in range(0, len(files), batch):
            part = files[i : i + batch]
            res = await client.post(
                f"/v1/kbs/{kb}/uploads",
                files=[
                    ("files", (p.name, await asyncio.to_thread(p.read_bytes), "application/octet-stream"))
                    for p in part
                ],
                data={"paths": [str(p.relative_to(directory)) for p in part]},
            )
            if res.status_code != 200:
                print(f"アップロード失敗: {res.status_code} {res.text}", file=sys.stderr)
                return 1
            for item in res.json()["items"]:
                if not quiet:
                    print(f"{item['status']:9s} {item['filename']}")
                if item["job_id"]:
                    jobs[item["job_id"]] = item["filename"]
        final: dict[str, dict[str, object]] = {}
        ids = list(jobs)
        for g in range(0, len(ids), SSE_IDS_PER_STREAM):
            group = ids[g : g + SSE_IDS_PER_STREAM]
            async with client.stream(
                "GET", "/v1/jobs/events", params={"ids": ",".join(group)}, timeout=timeout_sec
            ) as stream:
                async for line in stream.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    ev = json.loads(line[6:])
                    final[ev["job_id"]] = ev
                    if not quiet or ev.get("status") in ("ready", "error", "cancelled"):
                        detail = ev.get("stage_detail", "")
                        print(f"  [{ev.get('progress', ''):>3}] {jobs[ev['job_id']]}: {detail}")
            if len(ids) > SSE_IDS_PER_STREAM:
                print(f"進捗: {min(g + SSE_IDS_PER_STREAM, len(ids))}/{len(ids)} 件")
    elapsed = time.monotonic() - started
    ok = sum(1 for e in final.values() if e.get("status") == "ready")
    chunks = sum(int(e.get("chunk_count") or 0) for e in final.values())  # type: ignore[call-overload]
    print(f"完了: {ok}/{len(jobs)} 件 ready、子チャンク {chunks}、所要 {elapsed:.1f} 秒")
    return 0 if ok == len(jobs) else 2


async def gc(settings: Settings, *, retention_days: int | None) -> int:
    """ごみ箱の期限切れ削除と孤立内容の回収を今すぐ 1 回行う（ワーカーは 1 時間ごと）。"""
    days = settings.trash_retention_days if retention_days is None else retention_days
    engine = make_engine(settings.database_url)
    client = AsyncQdrantClient(url=settings.qdrant_url)
    try:
        async with make_sessionmaker(engine)() as s:
            counts = await run_gc(
                s,
                LocalStorage(settings.storage_dir),
                QdrantIndex(client, settings.qdrant_collection),
                now=datetime.now(UTC),
                retention=timedelta(days=days),
            )
        print(f"保持期間 {days} 日: " + json.dumps(counts, ensure_ascii=False))
        return 0
    finally:
        await client.close()
        await engine.dispose()


async def sync_payload(settings: Settings) -> int:
    """全内容の payload（document_ids / kb_ids）を DB に合わせ直す（specs/004-retrieval R5）。"""
    engine = make_engine(settings.database_url)
    client = AsyncQdrantClient(url=settings.qdrant_url)
    try:
        sm = make_sessionmaker(engine)
        async with sm() as s:
            hashes = list(await s.scalars(select(Content.content_hash).where(Content.status == "ready")))
        await QdrantPayloadSync(QdrantIndex(client, settings.qdrant_collection), sm).sync(hashes)
        print(f"同期しました: {len(hashes)} 件")
        return 0
    finally:
        await client.close()
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arag.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reindex", help="版の変わった内容を再索引する（再解析なし）")
    r.add_argument("--all", action="store_true", help="版に関係なく全件")
    r.add_argument("--content-hash", action="append", default=[], help="対象の内容ハッシュ（複数可）")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--heading-context", action="store_true", help="LLM の文脈が付かなかった内容だけ")
    d = sub.add_parser("ingest-dir", help="ディレクトリ内のファイルを API 経由で入庫し、完了まで待つ")
    d.add_argument("directory", type=Path)
    d.add_argument("--kb", required=True, help="入庫先 KB の ID")
    d.add_argument("--api", default=DEV_API_URL)
    d.add_argument("--user", default="cli-admin")
    d.add_argument("--role", default="admin", choices=["owner", "admin", "member"])
    d.add_argument("--batch", type=int, default=10)
    d.add_argument("--timeout", type=float, default=3600)
    g = sub.add_parser("gc", help="ごみ箱の期限切れ削除と孤立内容の回収を今すぐ実行する")
    g.add_argument("--retention-days", type=int, default=None, help="既定は ARAG_TRASH_RETENTION_DAYS")
    rp = sub.add_parser("reparse-report", help="保存済みの docling.json から解析の記録を作り直す")
    rp.add_argument("--content-hash", action="append", default=[], help="対象の内容ハッシュ（複数可）")
    sub.add_parser("sync-payload", help="Qdrant の payload（参照する文書・KB）を DB に合わせ直す")
    args = parser.parse_args(argv)
    if args.cmd == "sync-payload":
        return asyncio.run(sync_payload(Settings()))
    if args.cmd == "reparse-report":
        return asyncio.run(reparse_report(Settings(), hashes=args.content_hash))
    if args.cmd == "gc":
        return asyncio.run(gc(Settings(), retention_days=args.retention_days))
    if args.cmd == "reindex":
        return asyncio.run(
            reindex(
                Settings(),
                all_=args.all,
                hashes=args.content_hash,
                dry_run=args.dry_run,
                heading_context=args.heading_context,
            )
        )
    return asyncio.run(
        ingest_dir(
            args.directory,
            api=args.api,
            kb=args.kb,
            user=args.user,
            role=args.role,
            batch=args.batch,
            timeout_sec=args.timeout,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
