"""X-Request-Id の付与と JSON ログ（specs/001-p0-skeleton R7・R8）。"""

import json
import re
import uuid

import pytest
import structlog
from fastapi.testclient import TestClient

from arag.main import create_app
from arag.settings import Settings

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(settings=Settings(), checks=[]))


def test_incoming_request_id_is_echoed(client: TestClient) -> None:
    res = client.get("/healthz", headers={"X-Request-Id": "abc-123.def_4"})
    assert res.headers["X-Request-Id"] == "abc-123.def_4"


def test_missing_request_id_is_generated(client: TestClient) -> None:
    res = client.get("/healthz")
    assert UUID_RE.match(res.headers["X-Request-Id"])


@pytest.mark.parametrize("bad", ["has space", "x" * 129, "semi;colon", "<script>", ""])
def test_invalid_request_id_is_replaced(client: TestClient, bad: str) -> None:
    res = client.get("/healthz", headers={"X-Request-Id": bad})
    rid = res.headers["X-Request-Id"]
    assert rid != bad
    assert UUID_RE.match(rid)


def test_log_lines_are_json_with_request_id(client: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    rid = str(uuid.uuid4())
    client.get("/readyz", headers={"X-Request-Id": rid})
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    mine = [line for line in lines if line.get("request_id") == rid]
    assert mine, f"request_id 付きのログ行が無い: {lines}"
    for line in mine:
        assert {"ts", "level", "msg", "logger"} <= line.keys()


def test_request_id_does_not_leak_between_requests(client: TestClient) -> None:
    client.get("/healthz", headers={"X-Request-Id": "first"})
    assert structlog.contextvars.get_contextvars().get("request_id") is None
