"""検索評価の CLI（specs/004-retrieval R19〜R22）。api/ から実行する。

uv run python -m arag.eval ingest --suite agentic_rag_demo
uv run python -m arag.eval index  --suite agentic_rag_demo --variant no_context ruri_embed
uv run python -m arag.eval run    --suite agentic_rag_demo --variant default dbsf [--gate] [--save-baseline]
uv run python -m arag.eval prepare --suite beir_scifact   # 公開データの取得（eval/.cache/）
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
from qdrant_client import AsyncQdrantClient
from sqlalchemy import select

from arag.auth.principal import Principal
from arag.cli import ingest_dir
from arag.db.engine import make_engine, make_sessionmaker
from arag.db.models import KnowledgeBase
from arag.eval.dataset import Case, GoldenSuite, load_suite
from arag.eval.report import compare_table, diff_baseline, gate_failures, to_markdown
from arag.eval.runner import run_suite
from arag.eval.variants import build_collection, collection_drift, kb_chunk_ids, load_variants, search_deps
from arag.search.schemas import SearchHit, SearchRequest
from arag.search.service import search
from arag.settings import Settings

EVAL_USER = "eval-admin"
PRINCIPAL = Principal(user_id=EVAL_USER, role="admin")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def kb_name(suite: str) -> str:
    return f"評価: {suite}"


def suite_dir(root: Path, suite: str) -> Path:
    return root / "eval" / "suites" / suite


def golden_path(root: Path, suite: str) -> Path:
    """リポジトリ管理の golden、無ければ prepare が作った公開データの golden。"""
    p = suite_dir(root, suite) / "golden.yaml"
    return p if p.exists() else root / "eval" / ".cache" / suite / "golden.yaml"


def files_dir(root: Path, suite: GoldenSuite, gp: Path) -> Path:
    if not suite.files_dir:
        raise SystemExit("golden.yaml に files_dir がありません")
    p = Path(suite.files_dir)
    return p if p.is_absolute() else (root / p if (root / p).exists() else gp.parent / p)


def kb_suite_of(suite: str) -> str:
    return load_suite(golden_path(repo_root(), suite)).kb_suite or suite


async def find_kb(settings: Settings, suite: str) -> str | None:
    engine = make_engine(settings.database_url)
    try:
        async with make_sessionmaker(engine)() as s:
            kb = await s.scalar(
                select(KnowledgeBase.id).where(
                    KnowledgeBase.name == kb_name(suite),
                    KnowledgeBase.kind == "org",
                    KnowledgeBase.deleted_at.is_(None),
                )
            )
            return str(kb) if kb else None
    finally:
        await engine.dispose()


async def cmd_ingest(args: argparse.Namespace, settings: Settings) -> int:
    root = repo_root()
    gp = golden_path(root, args.suite)
    suite = load_suite(gp)
    if suite.kb_suite:
        print(f"{args.suite} は題集 {suite.kb_suite} の KB を使います（先にそちらを ingest）")
        return 0
    headers = {"X-Dev-User-Id": EVAL_USER, "X-Dev-Role": "admin"}
    async with httpx.AsyncClient(base_url=args.api, headers=headers, timeout=60) as c:
        kb = await find_kb(settings, args.suite)
        if kb is None:
            res = await c.post("/v1/kbs", json={"name": kb_name(args.suite)})
            res.raise_for_status()
            kb = str(res.json()["id"])
        ready: set[str] = set()
        cursor = None
        while True:
            params: dict[str, Any] = {"kb_id": kb, "limit": 200, "status": "ready"}
            if cursor:
                params["cursor"] = cursor
            page = (await c.get("/v1/documents", params=params)).json()
            ready |= {d["filename"] for d in page["items"]}
            cursor = page.get("next_cursor")
            if not cursor:
                break
    missing = set(suite.documents) - ready
    print(f"KB {kb_name(args.suite)}（{kb}）: ready {len(ready)} 件、未入庫 {len(missing)} 件")
    if not missing:
        return 0
    return await ingest_dir(
        files_dir(root, suite, gp),
        api=args.api,
        kb=kb,
        user=EVAL_USER,
        role="admin",
        batch=args.batch,
        timeout_sec=args.timeout,
        only=missing,
        quiet=len(missing) > 20,
    )


async def cmd_index(args: argparse.Namespace, settings: Settings) -> int:
    variants, models = load_variants(repo_root() / "eval" / "variants.yaml")
    kb = await find_kb(settings, kb_suite_of(args.suite))
    if kb is None:
        raise SystemExit(f"先に ingest してください（KB「{kb_name(args.suite)}」がありません）")
    engine = make_engine(settings.database_url)
    client = AsyncQdrantClient(url=settings.qdrant_url, timeout=120)
    try:
        async with make_sessionmaker(engine)() as s:
            for name in args.variant:
                v = variants[name]
                n = await build_collection(s, v, models, settings, client, kb)
                where = v.collection(settings.qdrant_collection)
                print(f"{name}: {'本番の索引を使う' if n == 0 else f'{n} 点を {where} に作成'}")
    finally:
        await client.close()
        await engine.dispose()
    return 0


async def cmd_run(args: argparse.Namespace, settings: Settings) -> int:
    root = repo_root()
    suite = load_suite(golden_path(root, args.suite))
    variants, models = load_variants(root / "eval" / "variants.yaml")
    kb = await find_kb(settings, suite.kb_suite or args.suite)
    if kb is None:
        raise SystemExit(f"先に ingest してください（KB「{kb_name(args.suite)}」がありません）")
    out_dir = Path(args.out) if args.out else root / "eval" / ".reports" / args.suite
    out_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.database_url)
    sm = make_sessionmaker(engine)
    client = AsyncQdrantClient(url=settings.qdrant_url, timeout=60)
    results: list[dict[str, Any]] = []
    failed = False
    try:
        # 別コレクションの variant は DB の子チャンクと一致するか確かめる
        # （再索引で子チャンク ID が変わると誤計測になる）
        async with sm() as s:
            ids = await kb_chunk_ids(s, kb)
        for name in args.variant:
            v = variants[name]
            if v.own_collection:
                missing, stale = await collection_drift(
                    client, v.collection(settings.qdrant_collection), kb, ids
                )
                if missing or stale:
                    raise SystemExit(
                        f"{name}: コレクションが古い（欠け {missing}・古い点 {stale}）。"
                        f"先に index --suite {suite.kb_suite or args.suite} --variant {name}"
                    )
        for name in args.variant:
            v = variants[name]
            deps = search_deps(v, models, settings, client)

            async def fn(case: Case, v: Any = v, deps: Any = deps) -> list[SearchHit]:
                req = SearchRequest(
                    query=case.rewritten or case.query,
                    kb_ids=[kb],  # type: ignore[list-item]
                    top_k=case.top_k,
                    candidate_k=max(args.candidate_k, case.top_k),
                    mode=v.mode,
                    include_section=True,
                )
                async with sm() as s:
                    return (await search(s, deps, PRINCIPAL, req)).hits

            result = await run_suite(suite, fn)
            result["variant"] = name
            results.append(result)
            (out_dir / f"{name}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (out_dir / f"{name}.md").write_text(to_markdown(result), encoding="utf-8")
            base = suite_dir(root, args.suite) / "baselines" / f"{name}.json"
            if base.exists():
                d = diff_baseline(result, json.loads(base.read_text(encoding="utf-8")))
                print(
                    f"[{name}] 基準値との差: "
                    + ", ".join(f"{k} {v:+.3f}" for k, v in d.items() if "ms" not in k)
                )
            if args.save_baseline:
                base.parent.mkdir(parents=True, exist_ok=True)
                agg = {k: round(x, 4) for k, x in result["aggregate"].items()}
                base.write_text(
                    json.dumps(
                        {"suite": args.suite, "variant": name, "aggregate": agg}, ensure_ascii=False, indent=2
                    )
                    + "\n",
                    encoding="utf-8",
                )
            if args.gate:
                fails = gate_failures(result, suite.thresholds)
                for f in fails:
                    print(f"[{name}] ゲート不合格: {f}")
                failed |= bool(fails)
    finally:
        await client.close()
        await engine.dispose()
    table = compare_table(results)
    # 言語別（E2a）: 題集に en / ja の題が混ざるときはタグ別の表も出す
    for tag in ("ja", "en"):
        sub = compare_table(results, tag=tag)
        if sub and sub != table and len({t for r in results for t in r.get("by_tag", {})} & {"ja", "en"}) > 1:
            table += f"\n\n#### {tag} の題のみ（n={results[0]['by_tag'][tag]['n']:.0f}）\n\n" + sub
    (out_dir / "compare.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    print(f"レポート: {out_dir}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="arag.eval")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest", help="題集の文書を評価用 KB に入庫する")
    i.add_argument("--suite", required=True)
    i.add_argument("--api", default="http://localhost:8100")
    i.add_argument("--batch", type=int, default=20)
    i.add_argument("--timeout", type=float, default=7200)
    x = sub.add_parser("index", help="variant 用の別コレクションを作る")
    x.add_argument("--suite", required=True)
    x.add_argument("--variant", nargs="+", required=True)
    r = sub.add_parser("run", help="題集を実行して指標と比較表を出す")
    r.add_argument("--suite", required=True)
    r.add_argument("--variant", nargs="+", default=["default"])
    r.add_argument("--candidate-k", type=int, default=50)
    r.add_argument("--gate", action="store_true")
    r.add_argument("--save-baseline", action="store_true")
    r.add_argument("--out")
    pr = sub.add_parser("prepare", help="公開データセットを取得して golden を作る")
    pr.add_argument("--suite", required=True)
    args = p.parse_args(argv)
    settings = Settings()
    if args.cmd == "ingest":
        return asyncio.run(cmd_ingest(args, settings))
    if args.cmd == "index":
        return asyncio.run(cmd_index(args, settings))
    if args.cmd == "prepare":
        from arag.eval.public import prepare

        return prepare(repo_root(), args.suite)
    return asyncio.run(cmd_run(args, settings))


if __name__ == "__main__":
    sys.exit(main())
