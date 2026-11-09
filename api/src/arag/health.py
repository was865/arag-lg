"""liveness（/healthz）と readiness（/readyz）。"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from arag.logging import get_logger
from arag.settings import Settings

log = get_logger(__name__)

CheckResult = Literal["ok", "fail", "skipped", "external"]


@dataclass(frozen=True)
class Check:
    """依存先 1 件の疎通確認。run=None は未設定（skipped）か外部 API（external、確かめない）。"""

    name: str
    run: Callable[[], Awaitable[bool]] | None
    external: bool = False


class Liveness(BaseModel):
    status: Literal["ok"]


class Readiness(BaseModel):
    status: Literal["ok", "unavailable"]
    checks: dict[str, CheckResult]


async def _run_one(check: Check, limit_sec: float) -> CheckResult:
    if check.run is None:
        return "external" if check.external else "skipped"
    try:
        async with asyncio.timeout(limit_sec):
            ok = await check.run()
    except TimeoutError:
        log.warning("readiness チェックがタイムアウト", check=check.name, timeout_sec=limit_sec)
        return "fail"
    except Exception:
        # 失敗の詳細（ホスト名など）は応答に載せずログにだけ残す
        log.warning("readiness チェックが失敗", check=check.name, exc_info=True)
        return "fail"
    if not ok:
        log.warning("readiness チェックが偽を返した", check=check.name)
    return "ok" if ok else "fail"


router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=Liveness)
async def healthz() -> Liveness:
    return Liveness(status="ok")


@router.get(
    "/readyz",
    response_model=Readiness,
    responses={503: {"model": Readiness, "description": "依存先のいずれかが利用不可"}},
)
async def readyz(request: Request) -> JSONResponse:
    checks: list[Check] = request.app.state.checks
    timeout: float = request.app.state.settings.ready_timeout_sec
    results = await asyncio.gather(*(_run_one(c, timeout) for c in checks))
    by_name = {c.name: r for c, r in zip(checks, results, strict=True)}
    ok = all(r != "fail" for r in results)
    body = Readiness(status="ok" if ok else "unavailable", checks=by_name)
    log.info("readiness 確認", status=body.status)
    return JSONResponse(body.model_dump(), status_code=200 if ok else 503)


# ── 実チェッカ ─────────────────────────────────────────────────────────────


def http_check(url: str) -> Callable[[], Awaitable[bool]]:
    async def run() -> bool:
        async with httpx.AsyncClient() as client:
            res = await client.get(url)
            return res.status_code == 200

    return run


def _postgres_check(dsn: str) -> Callable[[], Awaitable[bool]]:
    async def run() -> bool:
        import psycopg

        async with await psycopg.AsyncConnection.connect(dsn, connect_timeout=2) as conn:
            cur = await conn.execute("SELECT 1")
            row = await cur.fetchone()
            return row == (1,)

    return run


def _redis_check(url: str) -> Callable[[], Awaitable[bool]]:
    async def run() -> bool:
        import redis.asyncio as redis

        client = redis.from_url(url)
        try:
            return bool(await client.ping())
        finally:
            await client.aclose()

    return run


def build_checks(settings: Settings) -> list[Check]:
    from arag.inference import inference_checks  # 循環 import を避ける

    return [
        Check("postgres", _postgres_check(settings.database_url)),
        Check("qdrant", http_check(settings.qdrant_url.rstrip("/") + "/readyz")),
        Check("redis", _redis_check(settings.redis_url)),
        *inference_checks(settings),
    ]
