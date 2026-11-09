"""Better Auth の JWT を JWKS で検証する（specs/006-auth R15〜R17）。"""

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jwt.algorithms import OKPAlgorithm

from arag.auth.principal import CurrentPrincipal
from arag.auth.tokens import JwksCache, principal_from_jwt
from arag.errors import ApiError, install_error_handlers
from arag.settings import Settings

ISS = "http://localhost:3100"
AUD = "arag-api"


def _keypair(kid: str) -> tuple[Ed25519PrivateKey, dict[str, Any]]:
    key = Ed25519PrivateKey.generate()
    jwk = json.loads(OKPAlgorithm.to_jwk(key.public_key()))
    jwk |= {"kid": kid, "alg": "EdDSA"}
    return key, jwk


def _token(key: Ed25519PrivateKey, kid: str, **over: Any) -> str:
    now = int(time.time())
    claims = {
        "sub": "user-1",
        "iss": ISS,
        "aud": AUD,
        "iat": now,
        "exp": now + 900,
        "email": "a@example.com",
        "email_verified": True,
        "role": "admin",
    } | over
    return jwt.encode(
        {k: v for k, v in claims.items() if v is not None}, key, algorithm="EdDSA", headers={"kid": kid}
    )


class FakeFetch:
    def __init__(self, *jwks: dict[str, Any]) -> None:
        self.keys = list(jwks)
        self.calls = 0

    async def __call__(self) -> dict[str, Any]:
        self.calls += 1
        return {"keys": self.keys}


def _cache(fetch: Callable[[], Awaitable[dict[str, Any]]], now: list[float] | None = None) -> JwksCache:
    clock = now if now is not None else [1000.0]
    return JwksCache(fetch, min_refetch_sec=30, clock=lambda: clock[0])


async def test_valid_token_becomes_principal() -> None:
    key, jwk = _keypair("k1")
    p = await principal_from_jwt(_token(key, "k1"), _cache(FakeFetch(jwk)), issuer=ISS, audience=AUD)
    assert (p.user_id, p.role, p.email, p.email_verified, p.is_admin) == (
        "user-1",
        "admin",
        "a@example.com",
        True,
        True,
    )


async def test_unknown_role_is_member_and_missing_verified_is_false() -> None:
    key, jwk = _keypair("k1")
    token = _token(key, "k1", role="user", email_verified=None)
    p = await principal_from_jwt(token, _cache(FakeFetch(jwk)), issuer=ISS, audience=AUD)
    assert p.role == "member" and p.email_verified is False


@pytest.mark.parametrize(
    "over",
    [
        {"exp": int(time.time()) - 10},
        {"iss": "http://evil"},
        {"aud": "other"},
        {"sub": None},
    ],
)
async def test_bad_claims_are_rejected(over: dict[str, Any]) -> None:
    key, jwk = _keypair("k1")
    with pytest.raises(ApiError) as e:
        await principal_from_jwt(_token(key, "k1", **over), _cache(FakeFetch(jwk)), issuer=ISS, audience=AUD)
    assert e.value.status == 401


async def test_wrong_signature_and_garbage_are_rejected() -> None:
    _, jwk = _keypair("k1")
    other, _ = _keypair("k1")
    for token in (_token(other, "k1"), "not-a-jwt", ""):
        with pytest.raises(ApiError):
            await principal_from_jwt(token, _cache(FakeFetch(jwk)), issuer=ISS, audience=AUD)


async def test_hs256_token_is_rejected() -> None:
    _, jwk = _keypair("k1")
    token = jwt.encode(
        {"sub": "u", "iss": ISS, "aud": AUD, "exp": int(time.time()) + 60}, "x" * 40, headers={"kid": "k1"}
    )
    with pytest.raises(ApiError):
        await principal_from_jwt(token, _cache(FakeFetch(jwk)), issuer=ISS, audience=AUD)


async def test_jwks_is_cached_and_refetched_for_new_kid_at_most_every_30s() -> None:
    k1, j1 = _keypair("k1")
    k2, j2 = _keypair("k2")
    fetch = FakeFetch(j1)
    now = [1000.0]
    cache = _cache(fetch, now)
    await principal_from_jwt(_token(k1, "k1"), cache, issuer=ISS, audience=AUD)
    await principal_from_jwt(_token(k1, "k1"), cache, issuer=ISS, audience=AUD)
    assert fetch.calls == 1
    # 鍵の入れ替え直後: 30 秒以内は取り直さない
    fetch.keys.append(j2)
    now[0] += 5
    with pytest.raises(ApiError):
        await principal_from_jwt(_token(k2, "k2"), cache, issuer=ISS, audience=AUD)
    assert fetch.calls == 1
    now[0] += 30
    p = await principal_from_jwt(_token(k2, "k2"), cache, issuer=ISS, audience=AUD)
    assert p.user_id == "user-1" and fetch.calls == 2


async def test_concurrent_requests_share_one_fetch() -> None:
    # 初回の取得中に来た要求も、その取得結果で検証する（先に「取得済み」扱いにして 401 にしない）
    import asyncio

    key, jwk = _keypair("k1")
    calls = 0

    async def slow() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"keys": [jwk]}

    cache = _cache(slow)
    token = _token(key, "k1")
    got = await asyncio.gather(
        *(principal_from_jwt(token, cache, issuer=ISS, audience=AUD) for _ in range(5))
    )
    assert [p.user_id for p in got] == ["user-1"] * 5 and calls == 1


async def test_jwks_fetch_failure_is_401() -> None:
    async def boom() -> dict[str, Any]:
        raise OSError("down")

    key, _ = _keypair("k1")
    with pytest.raises(ApiError) as e:
        await principal_from_jwt(_token(key, "k1"), _cache(boom), issuer=ISS, audience=AUD)
    assert e.value.status == 401


def test_jwt_mode_reads_bearer_and_ignores_dev_headers() -> None:
    key, jwk = _keypair("k1")
    app = FastAPI()
    app.state.settings = Settings(auth_mode="jwt", auth_issuer=ISS, auth_audience=AUD)
    app.state.jwks = _cache(FakeFetch(jwk))
    install_error_handlers(app)

    @app.get("/me")
    async def me(p: CurrentPrincipal) -> dict[str, object]:
        return {"user_id": p.user_id, "role": p.role}

    c = TestClient(app)
    ok = c.get("/me", headers={"Authorization": f"Bearer {_token(key, 'k1')}"})
    assert ok.json() == {"user_id": "user-1", "role": "admin"}
    assert c.get("/me", headers={"X-Dev-User-Id": "u1"}).status_code == 401
    assert c.get("/me", headers={"Authorization": "Basic abc"}).status_code == 401
