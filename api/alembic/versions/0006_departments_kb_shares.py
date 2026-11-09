"""部門と共有 KB の共有リスト（specs/024）

今の見え方・書き方を変えないよう、生きている全社 KB に次を付ける。

- 「全員: 閲覧」
- 「管理」: 今の admin（auth.user があれば）と、その KB に文書を上げたことのある人
  （これまで全社 KB に書けたのは admin だけなので、その時点の admin。評価用の利用者もここで拾う）

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-09 23:50:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_departments")),
        sa.UniqueConstraint("name", name=op.f("uq_departments_name")),
        schema="app",
    )
    op.create_table(
        "department_members",
        sa.Column("department_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["app.departments.id"],
            name=op.f("fk_department_members_department_id_departments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("department_id", "user_id", name=op.f("pk_department_members")),
        schema="app",
    )
    op.create_index(
        op.f("ix_department_members_user_id"), "department_members", ["user_id"], unique=False, schema="app"
    )
    op.create_table(
        "kb_shares",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kb_id", sa.UUID(), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["kb_id"],
            ["app.knowledge_bases.id"],
            name=op.f("fk_kb_shares_kb_id_knowledge_bases"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kb_shares")),
        sa.UniqueConstraint(
            "kb_id", "subject_type", "subject_id", name=op.f("uq_kb_shares_kb_id_subject_type_subject_id")
        ),
        schema="app",
    )
    op.create_index(op.f("ix_kb_shares_kb_id"), "kb_shares", ["kb_id"], unique=False, schema="app")

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO app.kb_shares (id, kb_id, subject_type, subject_id, role, created_by)
            SELECT gen_random_uuid(), id, 'everyone', '', 'viewer', 'migration'
            FROM app.knowledge_bases WHERE kind = 'org' AND deleted_at IS NULL
            """
        )
    )
    managers = """
        SELECT DISTINCT d.kb_id, d.uploaded_by FROM app.documents d
        JOIN app.knowledge_bases k ON k.id = d.kb_id AND k.kind = 'org' AND k.deleted_at IS NULL
    """
    if bind.execute(sa.text("SELECT to_regclass('auth.user')")).scalar() is not None:
        managers += """
        UNION
        SELECT k.id, u.id FROM app.knowledge_bases k CROSS JOIN auth."user" u
        WHERE k.kind = 'org' AND k.deleted_at IS NULL AND u.role IN ('owner', 'admin')
        """
    bind.execute(
        sa.text(
            f"""
            INSERT INTO app.kb_shares (id, kb_id, subject_type, subject_id, role, created_by)
            SELECT gen_random_uuid(), m.kb_id, 'user', m.uid, 'manager', 'migration'
            FROM ({managers}) AS m(kb_id, uid)
            ON CONFLICT DO NOTHING
            """  # noqa: S608 — 組み立てるのは固定の SQL だけ
        )
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_kb_shares_kb_id"), table_name="kb_shares", schema="app")
    op.drop_table("kb_shares", schema="app")
    op.drop_index(op.f("ix_department_members_user_id"), table_name="department_members", schema="app")
    op.drop_table("department_members", schema="app")
    op.drop_table("departments", schema="app")
