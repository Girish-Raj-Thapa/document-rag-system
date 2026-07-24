import enum 
import uuid
from datetime import datetime


from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, Computed, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class DocumentStatus(str, enum.Enum):
    pending = "pending"
    uploaded = "uploaded"
    processing = "processing"
    processed = "processed"
    needs_review = "needs_review"
    failed = "failed"
    deleted = "deleted"


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Idempotency Key (SHA-256 Hash of the file + config state)
    content_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"), nullable=False, default=DocumentStatus.uploaded
    )

    # Metadata fields
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace = relationship("Workspace")
    uploaded_by_user = relationship("User")


class DocumentChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_chunks"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=True
    )

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_text: Mapped[str] = mapped_column(String, nullable=False)
    contextualized_text: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # 768 dimensions
    embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=False) 
    
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    embedding_model_version: Mapped[str | None] = mapped_column(String, nullable=True, default='v1-bge-base-en-v1.5')

    # PostgreSQL Computed Column for Full-Text Search
    fts_document: Mapped[object | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(raw_text, '') || ' ' || coalesce(contextualized_text, ''))", persisted=True)
    )

    __table_args__ = (
        UniqueConstraint("document_id", "content_hash", name="uq_chunk_per_document"),
        Index("ix_document_chunks_embedding_hnsw", "embedding", postgresql_using="hnsw", postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"embedding": "vector_cosine_ops"}),
        Index("ix_document_chunks_fts_document", "fts_document", postgresql_using="gin"),
        Index("ix_document_chunks_metadata_gin", "metadata_payload", postgresql_using="gin"),
        Index("ix_document_chunks_parent_chunk_id", "parent_chunk_id")
    )
