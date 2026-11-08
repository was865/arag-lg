"""X-Request-Id の受け取り・生成と、ログ文脈への束縛。"""

import re
import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from arag.logging import get_logger

_access_log = get_logger("arag.access")

HEADER = "x-request-id"
# ログ注入を防ぐため、受信値は安全な文字だけ・128 文字以内のときに限り採用する
_VALID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def resolve_request_id(raw: str | None) -> str:
    if raw and _VALID.match(raw):
        return raw
    return str(uuid.uuid4())


class RequestIdMiddleware:
    """純 ASGI ミドルウェア（SSE 等のストリーミング応答を妨げない）。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        raw = next(
            (v.decode("latin-1") for k, v in scope["headers"] if k.decode("latin-1").lower() == HEADER),
            None,
        )
        request_id = resolve_request_id(raw)
        scope.setdefault("state", {})["request_id"] = request_id

        status = 500
        started = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.append((HEADER.encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        with structlog.contextvars.bound_contextvars(request_id=request_id):
            try:
                await self.app(scope, receive, send_with_id)
            finally:
                # uvicorn のアクセスログは request_id を持てないため、ここで 1 行出す
                _access_log.info(
                    "request",
                    method=scope["method"],
                    path=scope["path"],
                    status=status,
                    duration_ms=round((time.perf_counter() - started) * 1000, 1),
                )
