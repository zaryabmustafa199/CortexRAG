"""
app/models/document.py
----------------------
Document, UploadJob, ParentChunk, LeafChunk, ChunkEmbedding models.

RLS Note:
  - documents, parent_chunks, leaf_chunks, chunk_embeddings all carry workspace_id
    (directly or via FK chain) and have RLS policies set in the migration.
  - The ChunkEmbedding.vector column uses pgvector's Vector type with
    dimension from settings.active_embed_dim.
  - model_name column allows multi-model support without hardcoding dimensions.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base


class DocumentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    METADATA_EXTRACTED = "METADATA_EXTRACTED"
    EMBEDDINGS_STORED = "EMBEDDINGS_STORED"
    READY = "READY"
    FAILED = "FAILED"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)  # MinIO object key
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(
            DocumentStatus, name="document_status", values_callable=lambda x: [e.value for e in x]
        ),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True,
    )
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)  # bytes
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="documents")  # type: ignore[name-defined]
    upload_job: Mapped[UploadJob] = relationship(
        "UploadJob", back_populates="document", uselist=False, cascade="all, delete-orphan"
    )
    parent_chunks: Mapped[list[ParentChunk]] = relationship(
        "ParentChunk", back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename!r} status={self.status}>"


class UploadJob(Base):
    __tablename__ = "upload_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="QUEUED", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    document: Mapped[Document] = relationship("Document", back_populates="upload_job")

    def __repr__(self) -> str:
        return f"<UploadJob id={self.id} status={self.status!r}>"


class ParentChunk(Base):
    __tablename__ = "parent_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        # Denormalised for RLS — eliminates JOIN when checking workspace isolation
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # LLM-generated section summary
    section_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    document: Mapped[Document] = relationship("Document", back_populates="parent_chunks")
    leaf_chunks: Mapped[list[LeafChunk]] = relationship(
        "LeafChunk", back_populates="parent", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ParentChunk id={self.id} doc={self.document_id} pages={self.page_start}-{self.page_end}>"


class LeafChunk(Base):
    __tablename__ = "leaf_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("parent_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        # Denormalised for RLS
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)  # order within parent
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    years_detected: Mapped[list[int] | None] = mapped_column(
        JSONB, nullable=True
    )  # e.g. [2015, 2020]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    parent: Mapped[ParentChunk] = relationship("ParentChunk", back_populates="leaf_chunks")
    embeddings: Mapped[list[ChunkEmbedding]] = relationship(
        "ChunkEmbedding", back_populates="chunk", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<LeafChunk id={self.id} parent={self.parent_id} idx={self.chunk_index}>"


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leaf_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        # Denormalised for RLS
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Vector dimension is set from settings — allows model switching without schema rebuild
    vector: Mapped[Any] = mapped_column(Vector(settings.active_embed_dim), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    chunk: Mapped[LeafChunk] = relationship("LeafChunk", back_populates="embeddings")

    # ── Table-level index (HNSW for vector cosine search) ─────────────────────
    # NOTE: The HNSW index cannot be expressed in SQLAlchemy mapped columns —
    # it is created manually in the Alembic migration using op.execute().
    __table_args__ = (Index("idx_chunk_embeddings_workspace_id", "workspace_id"),)

    def __repr__(self) -> str:
        return f"<ChunkEmbedding chunk={self.chunk_id} model={self.model_name!r}>"
