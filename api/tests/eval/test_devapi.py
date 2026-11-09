"""評価用 API（開発用ヘッダで認証する）の確認。"""

import httpx
import pytest

from arag.devapi import DEV_API_URL, DevApiUnavailable, check_dev_api


def client(handler) -> httpx.AsyncClient:  # type: ignore[no-untyped-def]
    return httpx.AsyncClient(base_url=DEV_API_URL, transport=httpx.MockTransport(handler))


def test_dev_api_url_is_local_eval_port() -> None:
    assert DEV_API_URL == "http://127.0.0.1:8101"


async def test_ok_when_dev_headers_accepted() -> None:
    async with client(lambda req: httpx.Response(200, json={"items": []})) as c:
        await check_dev_api(c)


async def test_jwt_api_explains_how_to_start_eval_api() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": "unauthenticated"}})

    async with client(handler) as c:
        with pytest.raises(DevApiUnavailable, match="make eval-api"):
            await check_dev_api(c)


async def test_unreachable_api_explains_how_to_start_eval_api() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=req)

    async with client(handler) as c:
        with pytest.raises(DevApiUnavailable, match="make eval-api"):
            await check_dev_api(c)
