"""回答に続けて聞く質問の候補（specs/028 R1）

messages に suggestions（JSONB、既定は空の配列）を足す。既存の回答は候補なし。

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-13 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "suggestions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        schema="app",
    )


def downgrade() -> None:
    op.drop_column("messages", "suggestions", schema="app")
