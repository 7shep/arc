import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, String, Text, UniqueConstraint
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
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


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
    course: Mapped[Course] = relationship(back_populates="documents")


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
    node_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    course: Mapped[Course] = relationship(back_populates="nodes")
    __table_args__ = (UniqueConstraint("course_id", "label", name="uq_course_node_label"),)


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    source_node_id: Mapped[str] = mapped_column(ForeignKey("graph_nodes.id", ondelete="CASCADE"))
    target_node_id: Mapped[str] = mapped_column(ForeignKey("graph_nodes.id", ondelete="CASCADE"))
    type: Mapped[GraphEdgeType] = mapped_column(Enum(GraphEdgeType))
    confidence: Mapped[float | None] = mapped_column(Float)
    edge_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    course: Mapped[Course] = relationship(back_populates="edges")
