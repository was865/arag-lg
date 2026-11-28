"""登録した MCP サーバとツールの読み出し（specs/032 design §3・§4）。"""

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
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


def definition_hash(name: str, description: str, input_schema: dict[str, Any], read_only: bool) -> str:
    """ツールの定義の指紋（specs/038 R1）。移行 0011 にも同じ式がある。"""
    raw = json.dumps(
        {"name": name, "description": description, "input_schema": input_schema, "read_only": read_only},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def approve(tool: McpTool, by: str, side_effect: str | None) -> None:
    """今の定義を審査した定義として固定する（038 R2）。"""
    tool.approved_hash = tool.def_hash
    tool.approved_description = tool.description
    tool.approved_input_schema = dict(tool.input_schema or {})
    tool.approved_read_only = tool.read_only
    tool.approved_by = by
    tool.approved_at = datetime.now(UTC)
    tool.side_effect = side_effect


async def _enabled_rows(session: AsyncSession) -> list[tuple[McpServer, McpTool]]:
    rows = await session.execute(
        select(McpServer, McpTool)
        .join(McpTool, McpTool.server_id == McpServer.id)
        .where(McpServer.enabled.is_(True), McpTool.enabled.is_(True))
        .order_by(McpServer.name, McpTool.name)
    )
    return [(srv, tool) for srv, tool in rows.all()]


async def load_tools(session: AsyncSession) -> list[ToolSpec]:
    """有効なサーバの、審査済みで読み取りの、使うと選ばれたツール（エージェントに組み込む順。038 R8）。

    説明は管理者の書き換えがあればそれ（R12）。
    """
    return [
        ToolSpec(
            server_spec(srv),
            tool.name,
            tool.model_description or tool.description,
            dict(tool.input_schema or {}),
        )
        for srv, tool in await _enabled_rows(session)
        if tool.usable
    ]


@dataclass(frozen=True)
class HeldTool:
    """使うと選ばれているのに、審査の後に定義が変わって渡さないツール（038 R4・R18）。"""

    server: str
    label: str
    name: str


async def load_held(session: AsyncSession) -> list[HeldTool]:
    return [
        HeldTool(srv.name, srv.label, tool.name)
        for srv, tool in await _enabled_rows(session)
        if tool.status == "changed"
    ]


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


async def user_departments(session: AsyncSession, user_id: str) -> tuple[frozenset[str], tuple[str, ...]]:
    """所属部門の ID と名前（共有の判定と、身元に入れる部門名）。"""
    rows = (
        await session.execute(
            select(Department.id, Department.name)
            .join(DepartmentMember, DepartmentMember.department_id == Department.id)
            .where(DepartmentMember.user_id == user_id)
            .order_by(Department.name)
        )
    ).all()
    return frozenset(str(r[0]) for r in rows), tuple(r[1] for r in rows)
