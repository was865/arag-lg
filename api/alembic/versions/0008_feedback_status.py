"""技術者への報告の状態（specs/028 R15）

message_feedback に status（open / resolved、既定 open）・resolved_by・resolved_at を足す。
一覧（新しい順・状態で絞る）のための索引も足す。

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-13 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "message_feedback",
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        schema="app",
    )
    op.add_column("message_feedback", sa.Column("resolved_by", sa.String(64), nullable=True), schema="app")
    op.add_column(
        "message_feedback",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        schema="app",
    )
    op.create_index("ix_message_feedback_list", "message_feedback", ["updated_at", "id"], schema="app")


def downgrade() -> None:
    op.drop_index("ix_message_feedback_list", table_name="message_feedback", schema="app")
    op.drop_column("message_feedback", "resolved_at", schema="app")
    op.drop_column("message_feedback", "resolved_by", schema="app")
    op.drop_column("message_feedback", "status", schema="app")
