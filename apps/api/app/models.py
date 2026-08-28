import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class DocumentType(StrEnum):
    LECTURE = "LECTURE"
    READING = "READING"
    ASSIGNMENT = "ASSIGNMENT"
    TUTORIAL = "TUTORIAL"
    PRACTICE = "PRACTICE"
    OTHER = "OTHER"


class ProcessingStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class ReviewStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class GraphNodeType(StrEnum):
    CONCEPT = "CONCEPT"
    LECTURE = "LECTURE"
    DOCUMENT = "DOCUMENT"
    EXAMPLE = "EXAMPLE"
    FORMULA = "FORMULA"
    ASSIGNMENT = "ASSIGNMENT"
    QUESTION = "QUESTION"


class GraphEdgeType(StrEnum):
    REQUIRES = "REQUIRES"
    RELATED_TO = "RELATED_TO"
    TAUGHT_IN = "TAUGHT_IN"
    DEFINED_IN = "DEFINED_IN"
    USED_IN = "USED_IN"
    EXAMPLE_OF = "EXAMPLE_OF"
    APPEARS_IN = "APPEARS_IN"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Course(TimestampMixin, Base):
    __tablename__ = "courses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    documents: Mapped[list["Document"]] = relationship(
        back_populates="course", cascade="all, delete"
    )
    nodes: Mapped[list["GraphNode"]] = relationship(back_populates="course", cascade="all, delete")
    edges: Mapped[list["GraphEdge"]] = relationship(back_populates="course", cascade="all, delete")


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType))
    mime_type: Mapped[str] = mapped_column(String(128))
    storage_path: Mapped[str] = mapped_column(String(500), unique=True)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus), default=ProcessingStatus.UPLOADED
    )
    processing_error: Mapped[str | None] = mapped_column(Text)
    course: Mapped[Course] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(TimestampMixin, Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(500))
    source_location: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    document: Mapped[Document] = relationship(back_populates="chunks")
    __table_args__ = (
        UniqueConstraint("document_id", "sequence", name="uq_document_chunk_sequence"),
    )


class GraphNode(TimestampMixin, Base):
    __tablename__ = "graph_nodes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    type: Mapped[GraphNodeType] = mapped_column(Enum(GraphNodeType))
    label: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    source_location: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus), default=ReviewStatus.APPROVED
    )
    node_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    course: Mapped[Course] = relationship(back_populates="nodes")
    __table_args__ = (UniqueConstraint("course_id", "label", name="uq_course_node_label"),)


class GraphEdge(TimestampMixin, Base):
    __tablename__ = "graph_edges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    source_node_id: Mapped[str] = mapped_column(ForeignKey("graph_nodes.id", ondelete="CASCADE"))
    target_node_id: Mapped[str] = mapped_column(ForeignKey("graph_nodes.id", ondelete="CASCADE"))
    type: Mapped[GraphEdgeType] = mapped_column(Enum(GraphEdgeType))
    confidence: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus), default=ReviewStatus.APPROVED
    )
    source_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    source_location: Mapped[str | None] = mapped_column(String(255))
    edge_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    course: Mapped[Course] = relationship(back_populates="edges")
    __table_args__ = (
        UniqueConstraint(
            "course_id", "source_node_id", "target_node_id", "type", name="uq_course_graph_edge"
        ),
    )


class GraphEvidence(Base):
    __tablename__ = "graph_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    graph_node_id: Mapped[str | None] = mapped_column(
        ForeignKey("graph_nodes.id", ondelete="CASCADE"), index=True
    )
    graph_edge_id: Mapped[str | None] = mapped_column(
        ForeignKey("graph_edges.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    source_location: Mapped[dict[str, Any]] = mapped_column(JSON)
    excerpt: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        CheckConstraint(
            "(graph_node_id IS NOT NULL AND graph_edge_id IS NULL) OR "
            "(graph_node_id IS NULL AND graph_edge_id IS NOT NULL)",
            name="ck_graph_evidence_one_target",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_evidence_confidence"),
    )
