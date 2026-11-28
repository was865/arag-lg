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
from arag.mcp.registry import SERVER_NAME, approve, department_names
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


ToolStatus = Literal["unreviewed", "approved", "changed"]
SideEffect = Literal["read", "write"]


class McpToolOut(BaseModel):
    name: str
    description: str = Field(description="サーバの今の説明")
    read_only_hint: bool = Field(description="サーバの読み取り専用の印（readOnlyHint）。参考")
    enabled: bool = Field(description="管理者の「使う」の選択")
    usable: bool = Field(description="エージェントに渡すか（審査済み・読み取り・使う）")
    input_schema: dict[str, object]
    fetched_at: datetime
    status: ToolStatus
    def_hash: str
    side_effect: SideEffect | None
    model_description: str | None
    approved_hash: str | None
    approved_description: str | None
    approved_input_schema: dict[str, object] | None
    approved_read_only: bool | None
    approved_by: str | None
    approved_at: datetime | None


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
    pending_review: int = Field(description="審査待ち（未審査と定義が変わった）のツールの数")
    tools: list[McpToolOut]
    shares: list[McpShareRow]


class McpAdminOut(BaseModel):
    identity_ready: bool = Field(description="身元の署名鍵（ARAG_MCP_IDENTITY_KEY）があるか")
    encryption_ready: bool = Field(description="トークンの暗号化鍵（ARAG_SECRET_KEY）があるか")
    servers: list[McpServerOut]


class McpToolsIn(BaseModel):
    enabled: list[str] = Field(max_length=200)


class McpToolReviewIn(BaseModel):
    tool: str = Field(min_length=1, max_length=64)
    def_hash: str = Field(description="管理者が見ていた定義の指紋（変わっていれば 409）")
    side_effect: SideEffect
    model_description: str | None = Field(default=None, max_length=2000)
    enabled: bool


class McpSharesIn(BaseModel):
    shares: list[McpShareRow] = Field(max_length=200)


# --- 一覧 ---


def _tool_out(t: McpTool) -> McpToolOut:
    return McpToolOut(
        name=t.name,
        description=t.description,
        read_only_hint=t.read_only,
        enabled=t.enabled,
        usable=t.usable,
        input_schema=t.input_schema,
        fetched_at=t.fetched_at,
        status=t.status,  # type: ignore[arg-type]
        def_hash=t.def_hash,
        side_effect=t.side_effect,  # type: ignore[arg-type]
        model_description=t.model_description,
        approved_hash=t.approved_hash,
        approved_description=t.approved_description,
        approved_input_schema=t.approved_input_schema,
        approved_read_only=t.approved_read_only,
        approved_by=t.approved_by,
        approved_at=t.approved_at,
    )


async def _server_out(ctx: CtxDep, srv: McpServer) -> McpServerOut:
    s = ctx.session
    tools = list(
        (await s.execute(select(McpTool).where(McpTool.server_id == srv.id).order_by(McpTool.name))).scalars()
    )
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
        pending_review=sum(t.status != "approved" for t in tools),
        tools=[_tool_out(t) for t in tools],
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
    changed = await refresh_server(ctx.session, settings, srv, caller)
    if changed:  # 審査の後に定義が変わった（specs/038 R4）。審査し直すまでエージェントに渡さない
        await ctx.audit(
            AuditEvent(
                action="mcp.tool.changed",
                resource_type="mcp_server",
                resource_id=str(srv.id),
                result="error",
                detail={"name": srv.name, "label": srv.label, "tools": changed},
            )
        )


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
    # 検査するのは新しく「使う」にするものだけ（定義が変わって止まっているツールの選択は残せる。specs/038 R4）
    newly = {n for n in want if not tools[n].enabled}
    pending = sorted(n for n in newly if tools[n].status != "approved")
    if pending:
        raise ApiError(422, "not_reviewed", f"審査していないツールは使えません: {', '.join(pending)}")
    writable = sorted(n for n in newly if tools[n].side_effect != "read")
    if writable:
        raise ApiError(
            422, "not_read", f"副作用が「読み取り」でないツールは使えません: {', '.join(writable)}"
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


@router.post("/v1/admin/mcp-servers/{server_id}/tools/review", response_model=McpServerOut)
async def review_tool(ctx: CtxDep, server_id: uuid.UUID, body: McpToolReviewIn) -> McpServerOut:
    """今の定義を審査する（specs/038 R7〜R11）。見ていた定義から変わっていれば受け付けない。"""
    _require_admin(ctx)
    srv = await _get(ctx, server_id)
    tool = await ctx.session.get(McpTool, (srv.id, body.tool))
    if tool is None:
        raise ApiError(404, "not_found", f"このサーバに無いツールです: {body.tool}")
    if tool.def_hash != body.def_hash:
        raise ApiError(
            409, "definition_moved", "見ている間にツールの定義が変わりました。読み直してから審査してください"
        )
    if body.enabled and body.side_effect != "read":
        raise ApiError(422, "not_read", "副作用が「読み取り」でないツールは使えません")
    before = tool.approved_hash
    approve(tool, ctx.principal.user_id, body.side_effect)
    text = (body.model_description or "").strip()
    tool.model_description = text or None
    tool.enabled = body.enabled
    await ctx.audit(
        AuditEvent(
            action="mcp.tool.review",
            resource_type="mcp_server",
            resource_id=str(srv.id),
            detail={
                "name": srv.name,
                "label": srv.label,
                "tool": tool.name,
                "side_effect": body.side_effect,
                "hash": tool.def_hash,
                "previous_hash": before,
                "read_only_hint": tool.read_only,
                "description_overridden": tool.model_description is not None,
                "enabled": tool.enabled,
            },
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
