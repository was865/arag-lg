"""社内システム（MCP サーバ）の登録の管理 API（specs/032 R8〜R11）。管理者のみ。操作は監査に残す。"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select

from arag.audit import AuditEvent
from arag.db.models import Department, McpServer, McpServerShare, McpTool
from arag.deps import CtxDep, get_settings
from arag.errors import ApiError
from arag.mcp.client import Caller
from arag.mcp.registry import SERVER_NAME, department_names
from arag.mcp.service import refresh_server
from arag.secrets import secret_box
from arag.settings import Settings

router = APIRouter(tags=["mcp-admin"])
SettingsDep = Annotated[Settings, Depends(get_settings)]

AuthKind = Literal["none", "identity", "bearer"]


def _require_admin(ctx: CtxDep) -> None:
    if not ctx.principal.is_admin:
        raise ApiError(403, "forbidden", "管理者だけが使えます")


# --- 入出力 ---


class McpServerIn(BaseModel):
    name: str = Field(description="英小文字・数字・_（32 文字まで）。ツール名の頭に付く")
    label: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    url: str = Field(min_length=8, max_length=500)
    auth_kind: AuthKind = "identity"
    token: str | None = Field(default=None, max_length=2000)
    timeout_sec: float | None = Field(default=None, ge=1, le=120)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not SERVER_NAME.match(v):
            raise ValueError("name は英小文字で始まり、英小文字・数字・_ で 32 文字まで")
        return v

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL は http:// か https:// で始めてください")
        return v.strip()


class McpServerPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    url: str | None = Field(default=None, min_length=8, max_length=500)
    auth_kind: AuthKind | None = None
    token: str | None = Field(default=None, min_length=1, max_length=2000)
    timeout_sec: float | None = Field(default=None, ge=1, le=120)
    enabled: bool | None = None


class McpToolOut(BaseModel):
    name: str
    description: str
    read_only: bool
    enabled: bool
    input_schema: dict[str, object]


class McpShareRow(BaseModel):
    subject_type: Literal["everyone", "department"]
    subject_id: str = ""
    name: str | None = Field(default=None, description="部門の名前（表示用）")


class McpServerOut(BaseModel):
    id: uuid.UUID
    name: str
    label: str
    description: str
    url: str
    auth_kind: str
    has_token: bool
    timeout_sec: float | None
    enabled: bool
    checked_at: datetime | None
    check_error: str | None
    tools: list[McpToolOut]
    shares: list[McpShareRow]


class McpAdminOut(BaseModel):
    identity_ready: bool = Field(description="身元の署名鍵（ARAG_MCP_IDENTITY_KEY）があるか")
    encryption_ready: bool = Field(description="トークンの暗号化鍵（ARAG_SECRET_KEY）があるか")
    servers: list[McpServerOut]


class McpToolsIn(BaseModel):
    enabled: list[str] = Field(max_length=200)


class McpSharesIn(BaseModel):
    shares: list[McpShareRow] = Field(max_length=200)


# --- 一覧 ---


async def _server_out(ctx: CtxDep, srv: McpServer) -> McpServerOut:
    s = ctx.session
    tools = (
        await s.execute(select(McpTool).where(McpTool.server_id == srv.id).order_by(McpTool.name))
    ).scalars()
    shares = list(
        (await s.execute(select(McpServerShare).where(McpServerShare.server_id == srv.id))).scalars()
    )
    dept_ids = [uuid.UUID(r.subject_id) for r in shares if r.subject_type == "department"]
    names = (
        dict(
            (await s.execute(select(Department.id, Department.name).where(Department.id.in_(dept_ids)))).all()
        )
        if dept_ids
        else {}
    )
    return McpServerOut(
        id=srv.id,
        name=srv.name,
        label=srv.label,
        description=srv.description,
        url=srv.url,
        auth_kind=srv.auth_kind,
        has_token=bool(srv.secret_enc),
        timeout_sec=srv.timeout_sec,
        enabled=srv.enabled,
        checked_at=srv.checked_at,
        check_error=srv.check_error,
        tools=[
            McpToolOut(
                name=t.name,
                description=t.description,
                read_only=t.read_only,
                enabled=t.enabled,
                input_schema=t.input_schema,
            )
            for t in tools
        ],
        shares=[
            McpShareRow(
                subject_type=r.subject_type,  # type: ignore[arg-type]
                subject_id=r.subject_id,
                name=names.get(uuid.UUID(r.subject_id)) if r.subject_type == "department" else None,
            )
            for r in sorted(shares, key=lambda r: (r.subject_type != "everyone", r.subject_id))
        ],
    )


@router.get("/v1/admin/mcp-servers", response_model=McpAdminOut)
async def list_servers(ctx: CtxDep, settings: SettingsDep) -> McpAdminOut:
    _require_admin(ctx)
    servers = (await ctx.session.execute(select(McpServer).order_by(McpServer.name))).scalars()
    return McpAdminOut(
        identity_ready=bool(settings.mcp_identity_key.get_secret_value()),
        encryption_ready=secret_box(settings) is not None,
        servers=[await _server_out(ctx, s) for s in servers],
    )


# --- 登録・編集 ---


def _encrypt_token(settings: Settings, token: str | None) -> str | None:
    if not token:
        return None
    box = secret_box(settings)
    if box is None:
        raise ApiError(503, "secret_key_missing", "暗号化の鍵（ARAG_SECRET_KEY）が設定されていません")
    return box.encrypt(token.strip())


async def _get(ctx: CtxDep, server_id: uuid.UUID) -> McpServer:
    srv = await ctx.session.get(McpServer, server_id)
    if srv is None:
        raise ApiError(404, "not_found", "社内システムが見つかりません")
    return srv


@router.post("/v1/admin/mcp-servers", response_model=McpServerOut, status_code=201)
async def create_server(ctx: CtxDep, settings: SettingsDep, body: McpServerIn) -> McpServerOut:
    _require_admin(ctx)
    exists = await ctx.session.scalar(select(McpServer.id).where(McpServer.name == body.name))
    if exists:
        raise ApiError(409, "name_taken", f"名前 {body.name} はすでに使われています")
    srv = McpServer(
        name=body.name,
        label=body.label.strip(),
        description=body.description.strip(),
        url=body.url,
        auth_kind=body.auth_kind,
        secret_enc=_encrypt_token(settings, body.token) if body.auth_kind == "bearer" else None,
        timeout_sec=body.timeout_sec,
        enabled=body.enabled,
        created_by=ctx.principal.user_id,
    )
    ctx.session.add(srv)
    await ctx.session.flush()
    await ctx.audit(
        AuditEvent(
            action="mcp.server.create",
            resource_type="mcp_server",
            resource_id=str(srv.id),
            detail={"name": srv.name, "label": srv.label, "url": srv.url, "auth_kind": srv.auth_kind},
        )
    )
    # 登録したら一度ツールの一覧を取る（取れなくても登録は残し、理由を見せる）
    await _refresh(ctx, settings, srv)
    await ctx.session.commit()
    return await _server_out(ctx, srv)


@router.patch("/v1/admin/mcp-servers/{server_id}", response_model=McpServerOut)
async def update_server(
    ctx: CtxDep, settings: SettingsDep, server_id: uuid.UUID, body: McpServerPatch
) -> McpServerOut:
    _require_admin(ctx)
    srv = await _get(ctx, server_id)
    changed = body.model_dump(exclude_unset=True, exclude={"token"})
    if "url" in changed and not str(changed["url"]).startswith(("http://", "https://")):
        raise ApiError(422, "invalid_url", "URL は http:// か https:// で始めてください")
    for k, v in changed.items():
        setattr(srv, k, v.strip() if isinstance(v, str) else v)
    if body.token is not None:
        srv.secret_enc = _encrypt_token(settings, body.token)
    if srv.auth_kind != "bearer":
        srv.secret_enc = None
    srv.updated_at = datetime.now(UTC)
    await ctx.audit(
        AuditEvent(
            action="mcp.server.update",
            resource_type="mcp_server",
            resource_id=str(srv.id),
            detail={
                "name": srv.name,
                "label": srv.label,
                "fields": sorted([*changed, *(["token"] if body.token else [])]),
            },
        )
    )
    await ctx.session.commit()
    return await _server_out(ctx, srv)


@router.delete("/v1/admin/mcp-servers/{server_id}", status_code=204)
async def delete_server(ctx: CtxDep, server_id: uuid.UUID) -> Response:
    _require_admin(ctx)
    srv = await _get(ctx, server_id)
    await ctx.audit(
        AuditEvent(
            action="mcp.server.delete",
            resource_type="mcp_server",
            resource_id=str(srv.id),
            detail={"name": srv.name, "label": srv.label},
        )
    )
    await ctx.session.delete(srv)
    await ctx.session.commit()
    return Response(status_code=204)


# --- ツール ---


async def _tools(ctx: CtxDep, server_id: uuid.UUID) -> list[McpTool]:
    return list((await ctx.session.execute(select(McpTool).where(McpTool.server_id == server_id))).scalars())


async def _refresh(ctx: CtxDep, settings: Settings, srv: McpServer) -> None:
    caller = Caller(ctx.principal.user_id, await department_names(ctx.session, ctx.principal.user_id))
    await refresh_server(ctx.session, settings, srv, caller)


@router.post("/v1/admin/mcp-servers/{server_id}/refresh", response_model=McpServerOut)
async def refresh_tools(ctx: CtxDep, settings: SettingsDep, server_id: uuid.UUID) -> McpServerOut:
    _require_admin(ctx)
    srv = await _get(ctx, server_id)
    await _refresh(ctx, settings, srv)
    await ctx.audit(
        AuditEvent(
            action="mcp.server.refresh",
            resource_type="mcp_server",
            resource_id=str(srv.id),
            result="ok" if srv.check_error is None else "error",
            detail={"name": srv.name, "label": srv.label, "error": srv.check_error},
        )
    )
    await ctx.session.commit()
    return await _server_out(ctx, srv)


@router.put("/v1/admin/mcp-servers/{server_id}/tools", response_model=McpServerOut)
async def set_tools(ctx: CtxDep, server_id: uuid.UUID, body: McpToolsIn) -> McpServerOut:
    _require_admin(ctx)
    srv = await _get(ctx, server_id)
    tools = {
        t.name: t
        for t in (await ctx.session.execute(select(McpTool).where(McpTool.server_id == srv.id))).scalars()
    }
    want = set(body.enabled)
    unknown = sorted(want - set(tools))
    if unknown:
        raise ApiError(422, "unknown_tool", f"このサーバに無いツールです: {', '.join(unknown)}")
    writable = sorted(n for n in want if not tools[n].read_only)
    if writable:
        raise ApiError(
            422,
            "not_read_only",
            f"読み取り専用の印（readOnlyHint）が無いツールは使えません: {', '.join(writable)}",
        )
    for name, t in tools.items():
        t.enabled = name in want
    await ctx.audit(
        AuditEvent(
            action="mcp.server.tools",
            resource_type="mcp_server",
            resource_id=str(srv.id),
            detail={"name": srv.name, "label": srv.label, "enabled": sorted(want)},
        )
    )
    await ctx.session.commit()
    return await _server_out(ctx, srv)


@router.put("/v1/admin/mcp-servers/{server_id}/shares", response_model=McpServerOut)
async def set_shares(ctx: CtxDep, server_id: uuid.UUID, body: McpSharesIn) -> McpServerOut:
    _require_admin(ctx)
    srv = await _get(ctx, server_id)
    rows: set[tuple[str, str]] = set()
    for r in body.shares:
        if r.subject_type == "everyone":
            rows.add(("everyone", ""))
            continue
        try:
            dept = await ctx.session.get(Department, uuid.UUID(r.subject_id))
        except ValueError:
            dept = None
        if dept is None:
            raise ApiError(422, "unknown_department", f"部門が見つかりません: {r.subject_id}")
        rows.add(("department", str(dept.id)))
    await ctx.session.execute(delete(McpServerShare).where(McpServerShare.server_id == srv.id))
    for st, sid in sorted(rows):
        ctx.session.add(McpServerShare(server_id=srv.id, subject_type=st, subject_id=sid))
    await ctx.audit(
        AuditEvent(
            action="mcp.server.shares",
            resource_type="mcp_server",
            resource_id=str(srv.id),
            detail={
                "name": srv.name,
                "label": srv.label,
                "shares": [f"{st}:{sid}" if sid else st for st, sid in sorted(rows)],
            },
        )
    )
    await ctx.session.commit()
    return await _server_out(ctx, srv)
