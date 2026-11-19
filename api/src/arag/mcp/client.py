"""MCP サーバへの接続（Streamable HTTP）。利用者の身元をヘッダで渡す（specs/032 §4）。

身元が利用者ごとに違うので MCP のセッションは使い回さないが、HTTP の接続（keep-alive）はサーバをまたいで
1 つの接続の池で使い回す（specs/033 R15）。要求ごとの httpx の client は身元のヘッダだけを持ち、池は閉じない。
身元の JWT には鍵の版（kid、ARAG_MCP_IDENTITY_KID、既定 k1）を付ける（033 R8。サーバは版で鍵を選ぶ）。
失敗は 3 種類に分けて返す:
止まっている（McpUnavailable）・時間切れ（McpTimeout）・身元を受け付けない（McpAuthError）。
"""

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

IDENTITY_ISSUER = "arag"
IDENTITY_TTL_SEC = 60


class McpError(Exception):
    pass


class McpUnavailable(McpError):
    """接続できない・5xx（止まっている）。"""


class McpTimeout(McpError):
    """待ち時間の上限を超えた。"""


class McpAuthError(McpError):
    """401・403（身元・トークンを受け付けない）。"""


@dataclass(frozen=True)
class Endpoint:
    name: str  # 身元の aud
    url: str
    auth_kind: str  # none / identity / bearer
    token: str | None = None  # bearer のとき（復号済み）


@dataclass(frozen=True)
class Caller:
    """呼び出す人（identity の身元に入れる）。"""

    user_id: str
    depts: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolInfo:
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool


@dataclass(frozen=True)
class CallResult:
    data: dict[str, Any] | None  # 構造化の結果（JSON のオブジェクト）
    text: str  # 本文（構造化が無いとき）
    is_error: bool


def identity_token(key: str, caller: Caller, audience: str, *, ttl_sec: int = IDENTITY_TTL_SEC) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": caller.user_id,
            "depts": list(caller.depts),
            "aud": audience,
            "iss": IDENTITY_ISSUER,
            "iat": now,
            "exp": now + timedelta(seconds=ttl_sec),
        },
        key,
        algorithm="HS256",
        headers={"kid": os.environ.get("ARAG_MCP_IDENTITY_KID", "k1")},
    )


class _SharedTransport(httpx.AsyncBaseTransport):
    """接続の池を共有する transport。client を閉じても池は閉じない（R15）。"""

    def __init__(self) -> None:
        self.pool: httpx.AsyncHTTPTransport | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    def _pool(self) -> httpx.AsyncHTTPTransport:
        loop = asyncio.get_running_loop()
        if self.pool is None or self.loop is not loop:  # イベントループごと（テストはループを作り直す）
            self.pool = httpx.AsyncHTTPTransport(
                limits=httpx.Limits(max_keepalive_connections=16, keepalive_expiry=30)
            )
            self.loop = loop
        return self.pool

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self._pool().handle_async_request(request)

    async def aclose(self) -> None:
        return None


SHARED = _SharedTransport()


def auth_headers(ep: Endpoint, caller: Caller, identity_key: str) -> dict[str, str]:
    if ep.auth_kind == "identity":
        if not identity_key:
            raise McpAuthError("身元の署名鍵（ARAG_MCP_IDENTITY_KEY）が設定されていません")
        return {"Authorization": f"Bearer {identity_token(identity_key, caller, ep.name)}"}
    if ep.auth_kind == "bearer" and ep.token:
        return {"Authorization": f"Bearer {ep.token}"}
    return {}


def _flatten(e: BaseException) -> list[BaseException]:
    if isinstance(e, BaseExceptionGroup):
        return [x for sub in e.exceptions for x in _flatten(sub)]
    return [e]


def _classify(e: BaseException) -> McpError:
    for x in _flatten(e):
        if isinstance(x, McpError):
            return x
        if isinstance(x, httpx.HTTPStatusError):
            code = x.response.status_code
            if code in (401, 403):
                return McpAuthError(f"HTTP {code}")
            return McpUnavailable(f"HTTP {code}")
        if isinstance(x, (httpx.TimeoutException, TimeoutError)):
            return McpTimeout("応答がありません")
        if isinstance(x, (httpx.TransportError, OSError)):
            return McpUnavailable(f"接続できません: {type(x).__name__}")
    first = _flatten(e)[0]
    return McpUnavailable(f"{type(first).__name__}: {first}")


async def _with_session(ep: Endpoint, headers: dict[str, str], limit_sec: float, work: Any) -> Any:
    async def run() -> Any:
        async with (
            httpx.AsyncClient(
                headers=headers, timeout=limit_sec, follow_redirects=True, transport=SHARED
            ) as http,
            streamable_http_client(ep.url, http_client=http) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            return await work(session)

    try:
        return await asyncio.wait_for(run(), timeout=limit_sec)
    except TimeoutError as e:
        raise McpTimeout(f"{limit_sec:g} 秒以内に応答がありません") from e
    except McpError:
        raise
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
            raise
        raise _classify(e) from e


async def ping(ep: Endpoint, headers: dict[str, str], limit_sec: float) -> None:
    async def work(_s: ClientSession) -> None:
        return None

    await _with_session(ep, headers, limit_sec, work)


async def list_tools(ep: Endpoint, headers: dict[str, str], limit_sec: float) -> list[ToolInfo]:
    async def work(s: ClientSession) -> list[ToolInfo]:
        res = await s.list_tools()
        return [
            ToolInfo(
                name=t.name,
                description=t.description or "",
                input_schema=dict(t.inputSchema or {}),
                read_only=bool(t.annotations and t.annotations.readOnlyHint),
            )
            for t in res.tools
        ]

    out: list[ToolInfo] = await _with_session(ep, headers, limit_sec, work)
    return out


def _structured(res: Any) -> dict[str, Any] | None:
    data = getattr(res, "structuredContent", None)
    if isinstance(data, dict):
        # FastMCP は型によって {"result": …} で包む
        if set(data) == {"result"} and isinstance(data["result"], dict):
            return data["result"]
        return data
    for c in getattr(res, "content", None) or []:
        if getattr(c, "type", "") == "text":
            try:
                parsed = json.loads(c.text)
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


async def call_tool(
    ep: Endpoint, headers: dict[str, str], tool: str, args: dict[str, Any], limit_sec: float
) -> CallResult:
    async def work(s: ClientSession) -> CallResult:
        res = await s.call_tool(tool, args)
        text = "\n".join(c.text for c in res.content if isinstance(c, TextContent))
        return CallResult(data=_structured(res), text=text, is_error=bool(res.isError))

    out: CallResult = await _with_session(ep, headers, limit_sec, work)
    return out
