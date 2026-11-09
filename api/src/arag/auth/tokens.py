"""Better Auth が発行する JWT の検証（specs/006-auth R15・R16）。

公開鍵は Better Auth の JWKS（/api/auth/jwks）から取り、キャッシュする。
未知の kid のときだけ取り直す（鍵の入れ替えに追従しつつ、偽の kid で JWKS を叩かせない）。
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

import httpx
import jwt
from jwt import PyJWK

from arag.auth.principal import ROLES, Principal, Role, unauthenticated

JwksFetch = Callable[[], Awaitable[dict[str, Any]]]


class JwksCache:
    def __init__(
        self, fetch: JwksFetch, *, min_refetch_sec: float = 30.0, clock: Callable[[], float] = time.monotonic
    ):
        self._fetch = fetch
        self._min_refetch = min_refetch_sec
        self._clock = clock
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at: float | None = None
        self._inflight: asyncio.Task[None] | None = None

    async def key(self, kid: str) -> PyJWK | None:
        if kid in self._keys:
            return self._keys[kid]
        # 取得中なら同じ取得を待つ（同時に来た要求を「取得済み」扱いで弾かない）
        if self._inflight is None:
            now = self._clock()
            if self._fetched_at is not None and now - self._fetched_at < self._min_refetch:
                return None
            self._fetched_at = now
            self._inflight = asyncio.ensure_future(self._refresh())
        task = self._inflight
        try:
            await asyncio.shield(task)
        finally:
            if task.done() and self._inflight is task:
                self._inflight = None
        return self._keys.get(kid)

    async def _refresh(self) -> None:
        data = await self._fetch()
        keys: dict[str, PyJWK] = {}
        for k in data.get("keys", []):
            if isinstance(k, dict) and k.get("kid"):
                keys[str(k["kid"])] = PyJWK(k, algorithm="EdDSA")
        self._keys = keys


def http_jwks_fetch(url: str, timeout: float = 5.0) -> JwksFetch:
    async def fetch() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.get(url)
            res.raise_for_status()
            return cast(dict[str, Any], res.json())

    return fetch


async def principal_from_jwt(token: str, cache: JwksCache, *, issuer: str, audience: str) -> Principal:
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if header.get("alg") != "EdDSA" or not isinstance(kid, str):
            raise unauthenticated()
        key = await cache.key(kid)
        if key is None:
            raise unauthenticated()
        claims = jwt.decode(
            token,
            key,
            algorithms=["EdDSA"],
            issuer=issuer,
            audience=audience,
            options={"require": ["sub", "exp", "iss", "aud"]},
        )
    except (jwt.PyJWTError, OSError, httpx.HTTPError, ValueError) as e:
        raise unauthenticated() from e
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub or len(sub) > 64:
        raise unauthenticated()
    role = claims.get("role")
    email = claims.get("email")
    return Principal(
        user_id=sub,
        role=cast(Role, role) if role in ROLES else "member",
        email=email if isinstance(email, str) else None,
        email_verified=claims.get("email_verified") is True,
    )
