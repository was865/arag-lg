"""依存ライセンスの走査（specs/001-p0-skeleton R18、授权原则）。

使い方:
  python scripts/check_licenses.py --pip pip.json --pnpm pnpm.json
    pip.json  … `pip-licenses --format=json`（本番依存のみの環境で実行）
    pnpm.json … `pnpm licenses list --prod --json`
禁止ライセンスを含む依存があれば終了コード 1。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# 禁止: AGPL / GPL（LGPL は除く）/ SSPL / BUSL / Elastic License
DENY = re.compile(
    r"AGPL|Affero|(?<![L])GPL|General Public License(?<!Lesser General Public License)|SSPL|"
    r"Server Side Public|BUSL|Business Source|Elastic",
    re.IGNORECASE,
)
LESSER = re.compile(r"LGPL|Lesser General Public", re.IGNORECASE)

# 個別に許可した依存（specs/000-overview/licenses.md と decisions.md §12 に根拠を記載）
ALLOW = {"psycopg", "psycopg-binary"}
# 自分自身（ライセンス未記載で UNKNOWN になる）
SELF = {"arag", "web"}


@dataclass(frozen=True)
class Dep:
    name: str
    version: str
    license: str


def is_denied(dep: Dep) -> bool:
    if dep.name.lower() in ALLOW:
        return False
    text = dep.license
    if LESSER.search(text):
        # LGPL は個別判断。許可リストに無ければ禁止扱い
        return True
    return bool(DENY.search(text))


def parse_pip(data: list[dict[str, str]]) -> list[Dep]:
    return [Dep(d["Name"], d["Version"], d["License"]) for d in data]


def parse_pnpm(data: dict[str, list[dict[str, object]]]) -> list[Dep]:
    deps: list[Dep] = []
    for license_name, pkgs in data.items():
        for p in pkgs:
            versions = p.get("versions") or [""]
            assert isinstance(versions, list)
            deps.append(Dep(str(p["name"]), str(versions[0]), license_name))
    return deps


def check(deps: list[Dep]) -> tuple[list[Dep], list[Dep]]:
    """(禁止, 不明) を返す。"""
    targets = [d for d in deps if d.name.lower() not in SELF]
    denied = [d for d in targets if is_denied(d)]
    unknown = [d for d in targets if d.license.strip().upper() in {"", "UNKNOWN"}]
    return denied, unknown


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pip", type=Path)
    ap.add_argument("--pnpm", type=Path)
    args = ap.parse_args(argv)
    deps: list[Dep] = []
    if args.pip:
        deps += parse_pip(json.loads(args.pip.read_text(encoding="utf-8")))
    if args.pnpm:
        deps += parse_pnpm(json.loads(args.pnpm.read_text(encoding="utf-8")))
    denied, unknown = check(deps)
    for d in unknown:
        print(f"警告: ライセンス不明 {d.name}=={d.version}（licenses.md で確認すること）")
    for d in denied:
        print(f"禁止: {d.name}=={d.version} ({d.license})")
    print(f"走査 {len(deps)} 件 / 禁止 {len(denied)} 件 / 不明 {len(unknown)} 件")
    return 1 if denied else 0


if __name__ == "__main__":
    sys.exit(main())
