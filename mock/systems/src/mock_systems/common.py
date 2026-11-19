"""模擬のサーバに共通の部品: 利用者の身元・時計・DB・結果の形（specs/032 design §2）。"""

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt

JST = timezone(timedelta(hours=9))
ISSUER = "arag"


# ── 身元 ──


class IdentityError(Exception):
    """身元が無い・署名が合わない・期限切れ・宛先が違う。"""


@dataclass(frozen=True)
class Identity:
    user_id: str
    depts: frozenset[str]

    def in_any(self, depts: frozenset[str]) -> bool:
        return bool(self.depts & depts)


def identity_key() -> str:
    key = os.environ.get("ARAG_MCP_IDENTITY_KEY", "")
    if not key:
        raise IdentityError("ARAG_MCP_IDENTITY_KEY が設定されていません")
    return key


def verify_identity(authorization: str | None, *, audience: str, key: str) -> Identity:
    """`Authorization: Bearer <JWT>` から身元を取り出す（HS256・`aud`・`exp`・`iss`）。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise IdentityError("身元（Bearer）がありません")
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["HS256"],
            audience=audience,
            issuer=ISSUER,
            options={"require": ["sub", "aud", "exp", "iss"]},
        )
    except jwt.PyJWTError as e:
        raise IdentityError(f"身元を確かめられません: {e}") from e
    depts = claims.get("depts") or []
    if not isinstance(depts, list) or not all(isinstance(d, str) for d in depts):
        raise IdentityError("depts が文字列の一覧ではありません")
    return Identity(user_id=str(claims["sub"]), depts=frozenset(depts))


def issue_identity(user_id: str, depts: list[str], *, audience: str, key: str, ttl_s: int = 60) -> str:
    """テストと手元の確かめ用（本番の発行は api 側）。"""
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user_id,
            "depts": depts,
            "aud": audience,
            "iss": ISSUER,
            "iat": now,
            "exp": now + timedelta(seconds=ttl_s),
        },
        key,
        algorithm="HS256",
    )


# ── 時計 ──


def today() -> date:
    """模擬の「今日」（MOCK_TODAY、既定 2026-11-18。評価の再現のため固定する）。"""
    return date.fromisoformat(os.environ.get("MOCK_TODAY", "2026-11-18"))


def now() -> datetime:
    """取得の時刻: 日付は模擬の今日、時:分は実際の時刻（JST）。"""
    real = datetime.now(JST)
    return datetime.combine(today(), real.time().replace(second=0, microsecond=0), tzinfo=JST)


# ── DB ──


def open_ro(path: Path) -> sqlite3.Connection:
    """読み取り専用で開く（書けない。R6）。"""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def like(term: str) -> str:
    return "%" + term.replace("%", "").replace("_", "").strip() + "%"


# ── 結果 ──


def table(
    system: str,
    title: str,
    columns: list[str],
    rows: list[list[Any]],
    *,
    basis: str,
    restricted: list[str] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """ツールの結果: 列名付きの行・件数・取得の時刻・時点の説明。"""
    out: dict[str, Any] = {
        "system": system,
        "title": title,
        "fetched_at": now().isoformat(timespec="minutes"),
        "basis": basis,
        "columns": columns,
        "rows": rows,
        "total": len(rows),
    }
    if restricted:
        out["restricted"] = restricted
    if note:
        out["note"] = note
    return out


def forbidden(system: str, message: str) -> dict[str, Any]:
    """権限が無いという返事（R16。api はこれを mcp_denied として記録する）。"""
    return {
        "system": system,
        "error": "forbidden",
        "message": message,
        "fetched_at": now().isoformat(timespec="minutes"),
    }


def current_basis(system: str) -> str:
    return f"{system} の現在の値（{now():%Y-%m-%d %H:%M} 取得）"
