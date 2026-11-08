"""/healthz と /readyz の振る舞い（specs/001-p0-skeleton R3〜R6）。"""

import asyncio

from fastapi.testclient import TestClient

from arag.health import Check
from arag.main import create_app
from arag.settings import Settings


def _check(name: str, result: bool | Exception | None, delay: float = 0.0) -> Check:
    """テスト用の偽チェック。result=None は未設定（skipped）を表す。"""

    async def run() -> bool:
        if delay:
            await asyncio.sleep(delay)
        if isinstance(result, Exception):
            raise result
        return bool(result)

    return Check(name=name, run=None if result is None else run)


def _client(*checks: Check, timeout: float = 2.0) -> TestClient:
    settings = Settings(ready_timeout_sec=timeout)
    return TestClient(create_app(settings=settings, checks=list(checks)))


def test_healthz_ok_without_checking_dependencies() -> None:
    # 依存が全滅していても liveness は 200
    client = _client(_check("postgres", False))
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_readyz_all_ok() -> None:
    client = _client(_check("postgres", True), _check("redis", True))
    res = client.get("/readyz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "checks": {"postgres": "ok", "redis": "ok"}}


def test_readyz_one_failure_returns_503() -> None:
    client = _client(_check("postgres", True), _check("redis", False))
    res = client.get("/readyz")
    assert res.status_code == 503
    assert res.json() == {"status": "unavailable", "checks": {"postgres": "ok", "redis": "fail"}}


def test_readyz_exception_is_fail_and_not_leaked() -> None:
    client = _client(_check("qdrant", RuntimeError("secret-host:6333 refused")))
    res = client.get("/readyz")
    assert res.status_code == 503
    assert res.json()["checks"] == {"qdrant": "fail"}
    assert "secret-host" not in res.text


def test_readyz_timeout_is_fail() -> None:
    client = _client(_check("tei_embed", True, delay=0.5), timeout=0.05)
    res = client.get("/readyz")
    assert res.status_code == 503
    assert res.json()["checks"] == {"tei_embed": "fail"}


def test_readyz_unconfigured_is_skipped_and_not_counted() -> None:
    client = _client(_check("postgres", True), _check("tei_embed", None))
    res = client.get("/readyz")
    assert res.status_code == 200
    assert res.json()["checks"] == {"postgres": "ok", "tei_embed": "skipped"}


def test_readyz_runs_checks_concurrently() -> None:
    # 0.3 秒のチェック 3 つが直列なら 0.9 秒超。並行なら上限 0.5 秒に収まる
    import time

    client = _client(*(_check(f"c{i}", True, delay=0.3) for i in range(3)), timeout=1.0)
    started = time.perf_counter()
    res = client.get("/readyz")
    assert res.status_code == 200
    assert time.perf_counter() - started < 0.6
