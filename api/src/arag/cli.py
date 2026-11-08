"""運用コマンド（R41・E1）。

python -m arag.cli reindex [--all | --content-hash H ...] [--dry-run]
python -m arag.cli ingest-dir DIR --kb KB_ID [--api URL] [--user ID --role admin]
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import or_, select

from arag.db.engine import make_engine, make_sessionmaker
from arag.db.models import Content, IngestJob
from arag.ingest import queue
from arag.ingest.chunking import CHUNKER_VERSION
from arag.ingest.sparse import SPARSE_VERSION
from arag.kb.uploads import SUPPORTED
from arag.settings import Settings


async def reindex(settings: Settings, *, all_: bool, hashes: list[str], dry_run: bool) -> int:
    """版の変わった内容を再投入する。保存済み docling.json を使うので再解析はしない。"""
    engine = make_engine(settings.database_url)
    sm = make_sessionmaker(engine)
    try:
        async with sm() as s:
            q = select(Content).where(Content.status.in_(["ready", "error"]))
            if hashes:
                q = q.where(Content.content_hash.in_(hashes))
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


def _list_files(directory: Path) -> list[Path]:
    return sorted(
        p for p in directory.rglob("*") if p.is_file() and p.suffix.lower().lstrip(".") in SUPPORTED
    )


async def ingest_dir(
    directory: Path, *, api: str, kb: str, user: str, role: str, batch: int, timeout_sec: float
) -> int:
    files = await asyncio.to_thread(_list_files, directory)
    if not files:
        print("対象ファイルがありません", file=sys.stderr)
        return 1
    headers = {"X-Dev-User-Id": user, "X-Dev-Role": role}
    started = time.monotonic()
    jobs: dict[str, str] = {}
    async with httpx.AsyncClient(base_url=api.rstrip("/"), headers=headers, timeout=600) as client:
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
                print(f"{item['status']:9s} {item['filename']}")
                if item["job_id"]:
                    jobs[item["job_id"]] = item["filename"]
        final: dict[str, dict[str, object]] = {}
        if jobs:
            async with client.stream(
                "GET", "/v1/jobs/events", params={"ids": ",".join(jobs)}, timeout=timeout_sec
            ) as stream:
                async for line in stream.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    ev = json.loads(line[6:])
                    final[ev["job_id"]] = ev
                    print(
                        f"  [{ev.get('progress', ''):>3}] {jobs[ev['job_id']]}: {ev.get('stage_detail', '')}"
                    )
    elapsed = time.monotonic() - started
    ok = sum(1 for e in final.values() if e.get("status") == "ready")
    chunks = sum(int(e.get("chunk_count") or 0) for e in final.values())  # type: ignore[call-overload]
    print(f"完了: {ok}/{len(jobs)} 件 ready、子チャンク {chunks}、所要 {elapsed:.1f} 秒")
    return 0 if ok == len(jobs) else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arag.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reindex", help="版の変わった内容を再索引する（再解析なし）")
    r.add_argument("--all", action="store_true", help="版に関係なく全件")
    r.add_argument("--content-hash", action="append", default=[], help="対象の内容ハッシュ（複数可）")
    r.add_argument("--dry-run", action="store_true")
    d = sub.add_parser("ingest-dir", help="ディレクトリ内のファイルを API 経由で入庫し、完了まで待つ")
    d.add_argument("directory", type=Path)
    d.add_argument("--kb", required=True, help="入庫先 KB の ID")
    d.add_argument("--api", default="http://localhost:8100")
    d.add_argument("--user", default="cli-admin")
    d.add_argument("--role", default="admin", choices=["owner", "admin", "member"])
    d.add_argument("--batch", type=int, default=10)
    d.add_argument("--timeout", type=float, default=3600)
    args = parser.parse_args(argv)
    if args.cmd == "reindex":
        return asyncio.run(reindex(Settings(), all_=args.all, hashes=args.content_hash, dry_run=args.dry_run))
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
