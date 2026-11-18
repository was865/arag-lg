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
    Float,
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
    """KB。kind: personal（所有者のみ）/ org（共有。誰が何をできるかは kb_shares。specs/024）。"""

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


class Department(Base):
    """部門（specs/024 R1）。入れ子にしない。"""

    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    created_at: Mapped[datetime] = _now()


class DepartmentMember(Base):
    """部門のメンバー。role: member / manager（部門管理者）。"""

    __tablename__ = "department_members"

    department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")


class KbShare(Base):
    """共有 KB の共有リストの 1 行（specs/024 R4・R5）。subject_id は everyone なら空文字。"""

    __tablename__ = "kb_shares"
    __table_args__ = (UniqueConstraint("kb_id", "subject_type", "subject_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    kb_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="")
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
    parse_warnings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """解析の体検で出た警告（warn 以上）の件数。null は記録なし（specs/030）"""
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


# --- 対話（specs/000-overview/data-model.md §3.2、specs/005-agent/design.md §5）---


class Thread(Base):
    """スレッド。LangGraph の thread_id と同じ値。"""

    __tablename__ = "threads"
    __table_args__ = (Index("ix_threads_user_list", "user_id", "pinned", "updated_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 共有（specs/008-thread-share）: private / org / public。トークンは一度出したら保つ
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default="private", server_default="private"
    )
    share_token: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class Message(Base):
    """1 ターン = 1 行。run の終了時に確定する（表示・分析用のビュー。状態の正は checkpoint）。"""

    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("thread_id", "ordinal"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    citation_map: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    no_answer_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 続けて聞く質問の候補（specs/028 R1）
    suggestions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    checkpoint_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = _now()


class Citation(Base):
    """引用（番号ごとの出典スナップショット。文書が消えても残すので文書へ FK は張らない）。分析用。"""

    __tablename__ = "citations"
    __table_args__ = (UniqueConstraint("message_id", "ordinal"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    section_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    document_title: Mapped[str] = mapped_column(Text, nullable=False)
    heading_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    snippet: Mapped[str] = mapped_column(Text, nullable=False, default="")
    block_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)


class MessageFeedback(Base):
    __tablename__ = "message_feedback"
    __table_args__ = (Index("ix_message_feedback_list", "updated_at", "id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rating: Mapped[str] = mapped_column(String(8), nullable=False)
    reason_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 技術者への報告の状態（specs/028 R15）: open / resolved。利用者が直したら open に戻す
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", server_default="open")
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class Run(Base):
    """エージェントの実行。run キューを兼ねる（specs/005-agent/design.md §1）。"""

    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_queued", "created_at", postgresql_where=text("status = 'queued'")),
        # 同じスレッドで同時に動く run は 1 つまで（R3）
        Index(
            "uq_runs_active_thread",
            "thread_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    heartbeat_at: Mapped[datetime | None] = _ts_nullable()
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _now()
    started_at: Mapped[datetime | None] = _ts_nullable()
    finished_at: Mapped[datetime | None] = _ts_nullable()


class LlmCredential(Base):
    """LLM の接続（API キーは暗号化して持つ。specs/013-llm-keys）。"""

    __tablename__ = "llm_credentials"

    id: Mapped[uuid.UUID] = _uuid_pk()
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_hint: Mapped[str | None] = mapped_column(String(8), nullable=True)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False, default="", server_default="")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class LlmModel(Base):
    """会話で選べるモデル（目録）。.env の ARAG_CHAT_MODELS より前に並ぶ。"""

    __tablename__ = "llm_models"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    credential_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_credentials.id", ondelete="RESTRICT"), nullable=True
    )
    kwargs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()
