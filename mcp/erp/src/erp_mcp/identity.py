"""ARag の身元の JWT を確かめる（specs/033 R8・design §4）。

HS256・`aud`（このサーバの名前）・`exp`・`iss`。鍵は版（`kid`）付きで複数持てる（入れ替えのあいだ新旧の両方を受ける）:
ERP_IDENTITY_KEYS="k2:<新しい鍵>,k1:<古い鍵>"。無ければ ARAG_MCP_IDENTITY_KEY を版 k1 として使う。
`kid` の無い JWT（032 の形）は既定の版（最初の鍵）で確かめる。受け取った JWT は ERP に渡さない（token passthrough の禁止）。
"""

import os
from dataclasses import dataclass

import jwt

ISSUER = "arag"


class IdentityError(Exception):
    pass


@dataclass(frozen=True)
class Identity:
    user_id: str
    depts: frozenset[str]
    kid: str


def keys_from_env() -> dict[str, str]:
    raw = os.environ.get("ERP_IDENTITY_KEYS", "")
    out: dict[str, str] = {}
    for part in raw.split(","):
        if ":" in part:
            kid, key = part.split(":", 1)
            if kid.strip() and key.strip():
                out[kid.strip()] = key.strip()
    if not out and os.environ.get("ARAG_MCP_IDENTITY_KEY"):
        out["k1"] = os.environ["ARAG_MCP_IDENTITY_KEY"]
    return out


def verify(authorization: str | None, *, audience: str, keys: dict[str, str]) -> Identity:
    if not keys:
        raise IdentityError("身元の鍵が設定されていません")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise IdentityError("身元（Bearer）がありません")
    token = authorization.split(" ", 1)[1].strip()
    try:
        kid = jwt.get_unverified_header(token).get("kid") or next(iter(keys))
    except jwt.PyJWTError as e:
        raise IdentityError(f"身元を読めません: {e}") from e
    key = keys.get(str(kid))
    if key is None:
        raise IdentityError(f"知らない鍵の版です（kid={kid}）")
    try:
        claims = jwt.decode(
            token, key, algorithms=["HS256"], audience=audience, issuer=ISSUER,
            options={"require": ["sub", "aud", "exp", "iss"]},
        )  # fmt: skip
    except jwt.PyJWTError as e:
        raise IdentityError(f"身元を確かめられません: {e}") from e
    depts = claims.get("depts") or []
    if not isinstance(depts, list) or not all(isinstance(d, str) for d in depts):
        raise IdentityError("depts が文字列の一覧ではありません")
    return Identity(str(claims["sub"]), frozenset(depts), str(kid))


def issue(user_id: str, depts: list[str], *, audience: str, key: str, kid: str = "k1", ttl_s: int = 60) -> str:
    """テストと手元の確かめ用（本番の発行は ARag の api・runner）。"""
    from datetime import UTC, datetime, timedelta

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
        headers={"kid": kid},
    )
