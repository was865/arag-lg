"""評価・CLI が叩く開発用 API（X-Dev-User-Id / X-Dev-Role で認証）。

本番の api は Better Auth の JWT で認証するため、開発用ヘッダは通らない。
評価用には compose の profile `eval` で別の api（ARAG_AUTH_MODE=dev）を 127.0.0.1 だけに立てる。
"""

import httpx

DEV_API_URL = "http://127.0.0.1:8101"

_HOW = "評価用の API を `make eval-api` で起動してください（終わったら `make eval-api-down`）"


class DevApiUnavailable(SystemExit):
    """開発用ヘッダが通る API に繋がらない。"""


async def check_dev_api(client: httpx.AsyncClient) -> None:
    """開発用ヘッダで認証できるか、最初に一度だけ確かめる。"""
    try:
        res = await client.get("/v1/kbs")
    except httpx.TransportError as e:
        raise DevApiUnavailable(f"{client.base_url} に接続できません。{_HOW}") from e
    if res.status_code == 401:
        raise DevApiUnavailable(
            f"{client.base_url} は開発用ヘッダを受け付けません（JWT 認証の api です）。{_HOW}"
        )
