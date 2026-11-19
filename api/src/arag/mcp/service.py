"""MCP サーバの登録の処理（管理 API と CLI で共有。specs/032 R8・R9）。"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.agent.catalog import secret_box
from arag.db.models import McpServer, McpServerShare, McpTool
from arag.mcp.client import Caller, McpError, auth_headers, list_tools
from arag.mcp.registry import server_spec
from arag.settings import Settings

# 模擬の社内システム（mock/systems、compose の mock-systems）。名前・表示名・ポート・説明
MOCK_SYSTEMS = [
    ("erp", "ERP（資材・購買）", 8201, "部品・在庫・入出庫・購買の発注（模擬）"),
    ("cmms", "保全システム", 8202, "設備・保全作業の記録・作業指示（模擬）"),
    ("directory", "社員名簿", 8203, "社員の部署・役職・内線（模擬）"),
    ("tickets", "課題の管理", 8204, "会議の決定事項・不具合の対策の課題と経過（模擬）"),
]


async def refresh_server(session: AsyncSession, settings: Settings, srv: McpServer, caller: Caller) -> None:
    """ツールの一覧を取り直す。新しい読み取り専用のツールは「使う」にする。消えたツールは外す（R9）。

    取れなければ check_error に理由を残し、ツールの一覧は変えない。
    """
    srv.checked_at = datetime.now(UTC)
    try:
        ep = server_spec(srv).endpoint(secret_box(settings))
        found = await list_tools(
            ep,
            auth_headers(ep, caller, settings.mcp_identity_key.get_secret_value()),
            srv.timeout_sec or settings.mcp_timeout_sec,
        )
    except McpError as e:
        srv.check_error = f"{type(e).__name__}: {e}"
        return
    srv.check_error = None
    old = {
        t.name: t
        for t in (await session.execute(select(McpTool).where(McpTool.server_id == srv.id))).scalars()
    }
    names = {t.name for t in found}
    for name, row in old.items():
        if name not in names:
            await session.delete(row)
    for t in found:
        cur = old.get(t.name)
        if cur is None:
            session.add(
                McpTool(
                    server_id=srv.id,
                    name=t.name,
                    description=t.description,
                    input_schema=t.input_schema,
                    read_only=t.read_only,
                    enabled=t.read_only,
                )
            )
        else:
            cur.description, cur.input_schema, cur.read_only = t.description, t.input_schema, t.read_only
            cur.enabled = cur.enabled and t.read_only
            cur.fetched_at = datetime.now(UTC)


async def register_mock(session: AsyncSession, settings: Settings, base_url: str) -> list[McpServer]:
    """模擬の 4 システムを登録する（あれば URL を合わせて取り直す）。使える範囲は「全員」。"""
    out = []
    for name, label, port, desc in MOCK_SYSTEMS:
        srv = await session.scalar(select(McpServer).where(McpServer.name == name))
        url = f"{base_url.rstrip('/')}:{port}/mcp"
        if srv is None:
            srv = McpServer(
                name=name, label=label, description=desc, url=url, auth_kind="identity", created_by="arag-cli"
            )
            session.add(srv)
            await session.flush()
            session.add(McpServerShare(server_id=srv.id, subject_type="everyone", subject_id=""))
        else:
            srv.url, srv.auth_kind, srv.enabled = url, "identity", True
            srv.updated_at = datetime.now(UTC)
        await refresh_server(session, settings, srv, Caller("arag-cli"))
        out.append(srv)
    await session.commit()
    return out
