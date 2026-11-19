"""設定（specs/033 R7）: 部門 → ERP の利用者（users.yaml）と、ERP ごとの項目の対応（<erp>.yaml）。"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from erp_mcp.model import ErpUser


def config_dir() -> Path:
    return Path(os.environ.get("ERP_CONFIG_DIR", Path(__file__).resolve().parents[2] / "config"))


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    return value


def load(name: str) -> dict[str, Any]:
    data = yaml.safe_load((config_dir() / f"{name}.yaml").read_text(encoding="utf-8")) or {}
    out: dict[str, Any] = _expand(data)
    return out


@dataclass(frozen=True)
class UserMap:
    rows: list[tuple[frozenset[str], ErpUser]]
    default: ErpUser

    def pick(self, depts: frozenset[str]) -> ErpUser:
        """身元の部門から ERP の利用者を選ぶ。どれにも当たらなければ最も狭い利用者（既定は拒否）。"""
        for match, user in self.rows:
            if depts & match:
                return user
        return self.default


def user_map(data: dict[str, Any] | None = None) -> UserMap:
    data = data if data is not None else load("users")
    deny = {k: frozenset(v or []) for k, v in (data.get("deny") or {}).items()}

    def user(login: str, hide: list[str] | None = None, note: str = "") -> ErpUser:
        return ErpUser(login, frozenset(hide or []), note, deny.get(login, frozenset()))

    rows = [
        (frozenset(r.get("depts") or []), user(r["login"], r.get("hide"), r.get("hide_note") or ""))
        for r in data.get("users") or []
    ]
    return UserMap(rows, user(data.get("default") or "erp-viewer"))
