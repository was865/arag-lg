"""社内システムのツールの審査と定義の固定（specs/038 R1〜R3・R7・R11）

mcp_tools に、今の定義の指紋・副作用・審査した定義・モデルに渡す説明の書き換えを足す。
既存の行は審査済みにする（審査した定義 = 今の定義。副作用は読み取り専用の印があれば read）。

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-28 10:00:00
"""

import hashlib
import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _hash(name: str, description: str, input_schema: Any, read_only: bool) -> str:
    # arag.mcp.registry.definition_hash と同じ式（移行はアプリのコードを import しない）
    raw = json.dumps(
        {"name": name, "description": description, "input_schema": input_schema, "read_only": read_only},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def upgrade() -> None:
    cols = [
        sa.Column("def_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("side_effect", sa.String(16), nullable=True),
        sa.Column("approved_hash", sa.String(64), nullable=True),
        sa.Column("approved_description", sa.Text(), nullable=True),
        sa.Column("approved_input_schema", postgresql.JSONB(), nullable=True),
        sa.Column("approved_read_only", sa.Boolean(), nullable=True),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_description", sa.Text(), nullable=True),
    ]
    for c in cols:
        op.add_column("mcp_tools", c, schema="app")
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT server_id, name, description, input_schema, read_only FROM app.mcp_tools")
    ).all()
    for server_id, name, desc, schema, ro in rows:
        h = _hash(name, desc, schema, bool(ro))
        conn.execute(
            sa.text(
                "UPDATE app.mcp_tools SET def_hash = :h, approved_hash = :h,"
                " approved_description = description,"
                " approved_input_schema = input_schema, approved_read_only = read_only,"
                " approved_by = 'migration-0011', approved_at = now(),"
                " side_effect = CASE WHEN read_only THEN 'read' ELSE NULL END"
                " WHERE server_id = :sid AND name = :n"
            ),
            {"h": h, "sid": server_id, "n": name},
        )


def downgrade() -> None:
    for name in (
        "model_description",
        "approved_at",
        "approved_by",
        "approved_read_only",
        "approved_input_schema",
        "approved_description",
        "approved_hash",
        "side_effect",
        "def_hash",
    ):
        op.drop_column("mcp_tools", name, schema="app")
