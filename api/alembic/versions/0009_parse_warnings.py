"""解析の体検の警告件数（specs/030 R6）

contents に parse_warnings（warn 以上の件数。null は記録なし）を足す。

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-14 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("contents", sa.Column("parse_warnings", sa.Integer(), nullable=True), schema="app")


def downgrade() -> None:
    op.drop_column("contents", "parse_warnings", schema="app")
