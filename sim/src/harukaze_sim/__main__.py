"""模擬器の入口（specs/034）。

    uv run python -m harukaze_sim sqlite <出力の .db>      # 大きい世界を SQLite に書く
    uv run python -m harukaze_sim odoo                    # Odoo に業務の流れとして入れる（033 の compose・profile erp）
    uv run python -m harukaze_sim docs <db> <出力のフォルダ> # ある時点の文書を world.db から作る
    uv run python -m harukaze_sim answers <db> <題集>      # 題の答えを計算して根拠を出す
環境変数: SIM_SEED（既定 20261118）
"""

import argparse
import os
import sys
from pathlib import Path

from harukaze_sim.run import simulate
from harukaze_sim.world import SIM_SEED


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="harukaze_sim")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sqlite")
    s.add_argument("out", type=Path)
    o = sub.add_parser("odoo")
    o.add_argument("--url", default=os.environ.get("ERP_ODOO_URL", "http://localhost:8069"))
    o.add_argument("--db", default=os.environ.get("ERP_ODOO_DB", "harukaze"))
    d = sub.add_parser("docs")
    d.add_argument("db", type=Path)
    d.add_argument("out", type=Path)
    a = sub.add_parser("answers")
    a.add_argument("db", type=Path)
    a.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    if args.cmd == "docs":
        from harukaze_sim.docs import generate

        for p in generate.all_docs(args.db, args.out):
            print(p)
        return 0
    if args.cmd == "answers":
        from harukaze_sim import answers

        return int(answers.main(args.db, args.out))
    seed = int(os.environ.get("SIM_SEED", SIM_SEED))
    world, events = simulate(seed)
    if args.cmd == "sqlite":
        from harukaze_sim.sinks import sqlite

        print(sqlite.write(args.out, world, events))
        return 0
    if args.cmd == "odoo":
        from harukaze_sim.sinks import odoo

        return odoo.load(world, events, url=args.url, db=args.db)
    return 2


if __name__ == "__main__":
    sys.exit(main())
