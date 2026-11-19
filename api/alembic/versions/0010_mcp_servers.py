"""社内システムの MCP サーバの登録（specs/032 R8〜R11）

mcp_servers・mcp_tools・mcp_server_shares を作る。

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-19 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("auth_kind", sa.String(16), nullable=False),
        sa.Column("secret_enc", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("timeout_sec", sa.Float(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_mcp_servers"),
        sa.UniqueConstraint("name", name="uq_mcp_servers_name"),
        schema="app",
    )
    op.create_table(
        "mcp_tools",
        sa.Column("server_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("input_schema", postgresql.JSONB(), nullable=False),
        sa.Column("read_only", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["server_id"],
            ["app.mcp_servers.id"],
            ondelete="CASCADE",
            name="fk_mcp_tools_server_id_mcp_servers",
        ),
        sa.PrimaryKeyConstraint("server_id", "name", name="pk_mcp_tools"),
        schema="app",
    )
    op.create_table(
        "mcp_server_shares",
        sa.Column("server_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["server_id"],
            ["app.mcp_servers.id"],
            ondelete="CASCADE",
            name="fk_mcp_server_shares_server_id_mcp_servers",
        ),
        sa.PrimaryKeyConstraint("server_id", "subject_type", "subject_id", name="pk_mcp_server_shares"),
        schema="app",
    )


def downgrade() -> None:
    op.drop_table("mcp_server_shares", schema="app")
    op.drop_table("mcp_tools", schema="app")
    op.drop_table("mcp_servers", schema="app")
