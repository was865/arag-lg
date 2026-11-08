"""app スキーマの ORM モデル。

specs/000-overview/data-model.md §3.1・§3.3、specs/003-ingestion/design.md §4。
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "app"


class Base(DeclarativeBase):
    metadata = MetaData(
        schema=SCHEMA,
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        },
    )


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _ts_nullable() -> Mapped[datetime | None]:
    return mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeBase(Base):
    """KB。kind: personal（所有者のみ）/ org（全社。書込は admin）。"""

    __tablename__ = "knowledge_bases"
    __table_args__ = (
        Index(
            "uq_knowledge_bases_personal_owner",
            "owner_user_id",
            unique=True,
            postgresql_where=text("kind = 'personal' AND deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    deleted_at: Mapped[datetime | None] = _ts_nullable()
    deleted_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = _now()


class Folder(Base):
    """KB 内の表示用ツリー（検索には影響しない）。"""

    __tablename__ = "folders"
    __table_args__ = (
        # 生存行だけの兄弟名一意。ルート直下は parent_id NULL を固定値に寄せて比較する。
        Index(
            "uq_folders_sibling_name",
            "kb_id",
            text("COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    kb_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    deleted_at: Mapped[datetime | None] = _ts_nullable()
    deleted_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = _now()


class Content(Base):
    """同一バイトのファイル実体（内容ハッシュ単位で 1 つ）。"""

    __tablename__ = "contents"

    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    mime: Mapped[str] = mapped_column(String(200), nullable=False)
    ext: Mapped[str] = mapped_column(String(16), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ref_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parser: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunker_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    embed_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sparse_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    indexed_at: Mapped[datetime | None] = _ts_nullable()
    created_at: Mapped[datetime] = _now()


class Document(Base):
    """KB 内の参照（ライブラリ項目）。引用・URL の識別子。"""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("kb_id", "content_hash"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    kb_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(ForeignKey("contents.content_hash"), nullable=False, index=True)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(64), nullable=False)
    deleted_at: Mapped[datetime | None] = _ts_nullable()
    deleted_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = _now()


class Section(Base):
    """親チャンク（章・節）。read_section / get_outline / 引用表示に使う。"""

    __tablename__ = "sections"
    __table_args__ = (Index("ix_sections_content_ordinal", "content_hash", "ordinal"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    content_hash: Mapped[str] = mapped_column(
        ForeignKey("contents.content_hash", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_len: Mapped[int] = mapped_column(Integer, nullable=False)


class Chunk(Base):
    """子チャンク（検索単位）。ベクトル化する本文は context + text。"""

    __tablename__ = "chunks"
    __table_args__ = (Index("ix_chunks_content_ordinal", "content_hash", "ordinal"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    content_hash: Mapped[str] = mapped_column(
        ForeignKey("contents.content_hash", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    block_type: Mapped[str] = mapped_column(String(16), nullable=False)
    heading_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    context_source: Mapped[str] = mapped_column(String(16), nullable=False, default="heading")
    token_len: Mapped[int] = mapped_column(Integer, nullable=False)
    boxes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class IngestJob(Base):
    """入庫ジョブ。ジョブキューを兼ねる（specs/003-ingestion/design.md §3.0）。"""

    __tablename__ = "ingest_jobs"
    __table_args__ = (
        Index("ix_ingest_jobs_queued", "run_after", postgresql_where=text("status = 'queued'")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    content_hash: Mapped[str] = mapped_column(
        ForeignKey("contents.content_hash", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage_detail: Mapped[str] = mapped_column(String(200), nullable=False, default="待機中")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    heartbeat_at: Mapped[datetime | None] = _ts_nullable()
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = _now()
    started_at: Mapped[datetime | None] = _ts_nullable()
    finished_at: Mapped[datetime | None] = _ts_nullable()


class AuditLog(Base):
    """監査ログ（追記専用）。対象が消えても残るよう FK は張らない。"""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_ts", "actor_id", "ts"),
        Index("ix_audit_logs_action_ts", "action", "ts"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    ts: Mapped[datetime] = _now()
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
