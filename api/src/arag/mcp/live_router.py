"""社内システムの今の値の API（specs/033 R17・R19・R21）。"""

import asyncio
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from arag.agent.service import get_thread
from arag.db.models import McpServer, Message
from arag.deps import CtxDep, get_settings
from arag.errors import ApiError, not_found
from arag.mcp import live
from arag.mcp.client import Caller
from arag.mcp.registry import server_spec, user_departments
from arag.secrets import secret_box
from arag.settings import Settings

router = APIRouter(tags=["mcp-live"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


class RefreshOut(BaseModel):
    n: int
    record: dict[str, Any] | None
    previous: dict[str, Any]
    changes: list[dict[str, Any]]
    error: str | None = None
    step: dict[str, Any]


@router.post("/v1/messages/{message_id}/records/{section_id}/refresh", response_model=RefreshOut)
async def refresh_record(
    message_id: uuid.UUID, section_id: str, ctx: CtxDep, settings: SettingsDep, request: Request
) -> RefreshOut:
    """出典の社内システムの記録（章）を、同じ利用者・同じツール・同じ引数で呼び直す（R17）。回答の文は変えない。

    章の id で指す（画面の引用番号は出た順に振り直しているため）。"""
    s = ctx.session
    msg = await s.get(Message, message_id)
    if msg is None:
        raise not_found()
    await get_thread(s, ctx.principal, msg.thread_id)
    n = live.section_n(msg, section_id)
    if n is None:
        raise ApiError(404, "not_found", "この章は回答の出典にありません")
    dept_ids, dept_names = await user_departments(s, ctx.principal.user_id)
    try:
        out = await live.refresh(
            s,
            msg,
            n,
            caller=Caller(ctx.principal.user_id, dept_names),
            dept_ids=dept_ids,
            identity_key=settings.mcp_identity_key.get_secret_value(),
            box=secret_box(settings),
            timeout_sec=settings.mcp_timeout_sec,
        )
    except LookupError as e:
        raise ApiError(404, "not_found", str(e)) from e
    await s.commit()
    if out["record"] is not None:
        server = str(out["record"].get("server") or "")
        redis = getattr(request.app.state, "redis", None)
        await live.put_health(redis, server, None, int(out["step"]["duration_ms"]))
    return RefreshOut(**out)


class SystemStatus(BaseModel):
    name: str
    label: str
    state: Literal["ok", "slow", "down"]
    ms: int
    checked_at: str
    reason: str | None = None


class SystemsStatusOut(BaseModel):
    systems: list[SystemStatus]


@router.get("/v1/systems/status", response_model=SystemsStatusOut)
async def systems_status(ctx: CtxDep, settings: SettingsDep, request: Request) -> SystemsStatusOut:
    """この利用者が使える社内システムと、それぞれの接続の状態（R19）。30 秒より古ければここで確かめ直す。"""
    redis = getattr(request.app.state, "redis", None)
    dept_ids, dept_names = await user_departments(ctx.session, ctx.principal.user_id)
    servers = await live.usable_servers(ctx.session, dept_ids)
    caller = Caller(ctx.principal.user_id, dept_names)
    key = settings.mcp_identity_key.get_secret_value()
    box = secret_box(settings)

    async def one(srv: McpServer) -> SystemStatus:
        h = await live.get_health(redis, srv.name)
        if h is None:
            h = await live.check_health(server_spec(srv), caller, key, box)
            await live.put_health(redis, srv.name, h.reason, h.ms)
        return SystemStatus(
            name=srv.name,
            label=srv.label,
            state=h.state,
            ms=h.ms,
            checked_at=h.at,
            reason=h.reason,
        )

    return SystemsStatusOut(systems=list(await asyncio.gather(*(one(x) for x in servers))))


class McpStatsOut(BaseModel):
    server: str
    hours: int
    calls: int
    failures: int
    failure_rate: float
    p50_ms: int | None
    p95_ms: int | None
    recent: list[dict[str, Any]]


@router.get("/v1/admin/mcp-servers/{server_id}/stats", response_model=McpStatsOut)
async def mcp_stats(server_id: uuid.UUID, ctx: CtxDep, hours: int = 1) -> McpStatsOut:
    """システムごとの直近の呼び出しの数・失敗の率・所要時間（R21。ARag 側の記録から集計）。"""
    if not ctx.principal.is_admin:
        raise ApiError(403, "forbidden", "管理者だけが使えます")
    srv = await ctx.session.scalar(select(McpServer).where(McpServer.id == server_id))
    if srv is None:
        raise not_found()
    return McpStatsOut(**await live.server_stats(ctx.session, srv.name, hours=max(1, min(hours, 24 * 7))))
