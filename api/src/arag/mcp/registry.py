"""登録した MCP サーバとツールの読み出し（specs/032 design §3・§4）。"""

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.db.models import Department, DepartmentMember, McpServer, McpServerShare, McpTool
from arag.mcp.client import Endpoint
from arag.secrets import SecretBox

SERVER_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
SEP = "__"  # エージェントのツール名: <サーバ名>__<ツール名>


def agent_tool_name(server: str, tool: str) -> str:
    """LLM のツール名に使える形（英数字・_・-、64 文字まで）。"""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", tool)
    return f"{server}{SEP}{safe}"[:64]


def is_mcp_tool(name: str) -> bool:
    return SEP in name


def server_of(name: str) -> str:
    return name.split(SEP, 1)[0]


@dataclass(frozen=True)
class ServerSpec:
    id: uuid.UUID
    name: str
    label: str
    url: str
    auth_kind: str
    secret_enc: str | None
    timeout_sec: float | None
    # 管理者が書いたシステムの説明（プロンプトに添えて、どのシステムに何があるかを選ばせる）
    description: str = ""

    def endpoint(self, box: SecretBox | None) -> Endpoint:
        token = (
            box.decrypt(self.secret_enc) if (box and self.secret_enc and self.auth_kind == "bearer") else None
        )
        return Endpoint(name=self.name, url=self.url, auth_kind=self.auth_kind, token=token)


@dataclass(frozen=True)
class ToolSpec:
    server: ServerSpec
    name: str  # サーバ上の名前
    description: str
    input_schema: dict[str, Any] = field(hash=False)

    @property
    def agent_name(self) -> str:
        return agent_tool_name(self.server.name, self.name)


async def load_tools(session: AsyncSession) -> list[ToolSpec]:
    """有効なサーバの、選ばれた読み取り専用のツール（エージェントに組み込む順）。"""
    rows = (
        await session.execute(
            select(McpServer, McpTool)
            .join(McpTool, McpTool.server_id == McpServer.id)
            .where(McpServer.enabled.is_(True), McpTool.enabled.is_(True), McpTool.read_only.is_(True))
            .order_by(McpServer.name, McpTool.name)
        )
    ).all()
    out = []
    for srv, tool in rows:
        out.append(ToolSpec(server_spec(srv), tool.name, tool.description, dict(tool.input_schema or {})))
    return out


def server_spec(srv: McpServer) -> ServerSpec:
    return ServerSpec(
        srv.id,
        srv.name,
        srv.label,
        srv.url,
        srv.auth_kind,
        srv.secret_enc,
        srv.timeout_sec,
        srv.description or "",
    )


def catalog_key(tools: list[ToolSpec]) -> str:
    """ツールの目録の指紋（runner のエージェントのキャッシュの鍵）。"""
    raw = json.dumps(
        [
            [t.server.name, t.server.label, t.server.description, t.name, t.description, t.input_schema]
            for t in tools
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def usable_server_ids(session: AsyncSession, department_ids: frozenset[str]) -> set[uuid.UUID]:
    """利用者が使えるサーバ（共有の行が「全員」か、所属する部門。R10）。"""
    rows = (await session.execute(select(McpServerShare))).scalars()
    return {
        r.server_id
        for r in rows
        if r.subject_type == "everyone" or (r.subject_type == "department" and r.subject_id in department_ids)
    }


async def department_names(session: AsyncSession, user_id: str) -> tuple[str, ...]:
    rows = await session.execute(
        select(Department.name)
        .join(DepartmentMember, DepartmentMember.department_id == Department.id)
        .where(DepartmentMember.user_id == user_id)
        .order_by(Department.name)
    )
    return tuple(rows.scalars())
