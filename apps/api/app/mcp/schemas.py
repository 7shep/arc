from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models import (
    DocumentType,
    GraphEdgeType,
    GraphNodeType,
    ProcessingStatus,
    ReviewStatus,
)


class SourceLocation(BaseModel):
    page: int | None = Field(default=None, ge=1)
    section: str | None = Field(default=None, min_length=1, max_length=500)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=1)

    @field_validator("section", mode="before")
    @classmethod
    def strip_section(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_location(self) -> "SourceLocation":
        if not any(
            value is not None
            for value in (self.page, self.section, self.start_offset, self.end_offset)
        ):
            raise ValueError("at least one source location field is required")
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("start_offset and end_offset must be provided together")
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset <= self.start_offset
        ):
            raise ValueError("end_offset must be greater than start_offset")
        return self


class DocumentResult(BaseModel):
    id: UUID
    course_id: UUID
    original_filename: str
    document_type: DocumentType
    mime_type: str
    processing_status: ProcessingStatus
    processing_error: str | None
    created_at: datetime
    updated_at: datetime


class DocumentListResult(BaseModel):
    documents: list[DocumentResult]


class DocumentChunkResult(BaseModel):
    id: UUID
    document_id: UUID
    sequence: int
    content: str
    source_location: dict[str, Any]


class DocumentChunksResult(BaseModel):
    chunks: list[DocumentChunkResult]


class EvidenceResult(BaseModel):
    id: UUID
    target_type: Literal["node", "relationship"]
    target_id: UUID
    document_id: UUID
    source_location: SourceLocation
    excerpt: str
    confidence: float


class CandidateNodeResult(BaseModel):
    id: UUID
    course_id: UUID
    node_type: GraphNodeType
    label: str
    description: str | None
    review_status: ReviewStatus
    confidence: float
    evidence: EvidenceResult


class CandidateRelationshipResult(BaseModel):
    id: UUID
    course_id: UUID
    source_node_id: UUID
    target_node_id: UUID
    relationship_type: GraphEdgeType
    review_status: ReviewStatus
    confidence: float
    evidence: EvidenceResult


class DocumentStatusResult(BaseModel):
    document_id: UUID
    processing_status: ProcessingStatus
    processing_error: str | None
