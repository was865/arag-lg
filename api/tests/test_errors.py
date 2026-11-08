"""共通エラー応答 {"error": {code, message}}（specs/003-ingestion design §5）。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from arag.errors import ApiError, install_error_handlers


def _client() -> TestClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise ApiError(409, "folder_name_conflict", "同じ名前のフォルダが既にあります")

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("secret internal detail")

    class Body(BaseModel):
        name: str

    @app.post("/body")
    async def body(b: Body) -> Body:
        return b

    return TestClient(app, raise_server_exceptions=False)


def test_api_error_shape() -> None:
    res = _client().get("/boom")
    assert res.status_code == 409
    assert res.json() == {
        "error": {"code": "folder_name_conflict", "message": "同じ名前のフォルダが既にあります"}
    }


def test_not_found_route_uses_shape() -> None:
    res = _client().get("/nope")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_validation_error_uses_shape() -> None:
    res = _client().post("/body", json={})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "invalid_request"


def test_unhandled_error_does_not_leak_detail() -> None:
    res = _client().get("/crash")
    assert res.status_code == 500
    assert res.json()["error"]["code"] == "internal_error"
    assert "secret" not in res.text
