from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import DocumentType, GraphEdgeType, GraphNodeType, ProcessingStatus, ReviewStatus


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)


class CourseCreate(ApiModel):
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(min_length=2, max_length=32)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        value = value.strip().upper().replace(" ", "")
        if not value:
            raise ValueError("must not be blank")
        return value


class CourseRead(ApiModel):
    id: str
    name: str
    code: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    document_count: int = 0
    node_count: int = 0
    edge_count: int = 0


class DocumentRead(ApiModel):
    id: str
    course_id: str
    filename: str
    original_filename: str
    document_type: DocumentType
    mime_type: str
    storage_path: str
    processing_status: ProcessingStatus
    processing_error: str | None
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime


class DocumentChunkRead(ApiModel):
    id: str
    document_id: str
    course_id: str
    content: str
    sequence: int
    page_number: int | None
    section: str | None
    source_location: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class GraphNodeRead(ApiModel):
    id: str
    course_id: str
    type: GraphNodeType
    label: str
    description: str | None
    source_document_id: str | None
    source_location: str | None
    confidence: float | None
    review_status: ReviewStatus
    metadata: dict[str, Any] = Field(validation_alias="node_metadata")
    created_at: datetime
    updated_at: datetime


class GraphNodeCreate(ApiModel):
    type: GraphNodeType
    label: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    source_document_id: str | None = None
    source_location: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def validate_source(self) -> "GraphNodeCreate":
        if self.source_location and not self.source_document_id:
            raise ValueError("sourceDocumentId is required when sourceLocation is provided")
        return self


class GraphNodeUpdate(ApiModel):
    type: GraphNodeType | None = None
    label: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    source_document_id: str | None = None
    source_location: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def validate_update(self) -> "GraphNodeUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class GraphEdgeRead(ApiModel):
    id: str
    course_id: str
    source_node_id: str
    target_node_id: str
    type: GraphEdgeType
    confidence: float | None
    review_status: ReviewStatus
    source_document_id: str | None
    source_location: str | None
    metadata: dict[str, Any] = Field(validation_alias="edge_metadata")
    created_at: datetime
    updated_at: datetime


class GraphRelationshipCreate(ApiModel):
    source_node_id: str
    target_node_id: str
    type: GraphEdgeType
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_document_id: str | None = None
    source_location: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_relationship(self) -> "GraphRelationshipCreate":
        if self.source_node_id == self.target_node_id:
            raise ValueError("sourceNodeId and targetNodeId must be different")
        if self.source_location and not self.source_document_id:
            raise ValueError("sourceDocumentId is required when sourceLocation is provided")
        return self


class GraphRelationshipUpdate(ApiModel):
    source_node_id: str | None = None
    target_node_id: str | None = None
    type: GraphEdgeType | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_document_id: str | None = None
    source_location: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_update(self) -> "GraphRelationshipUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class GraphRead(ApiModel):
    nodes: list[GraphNodeRead]
    edges: list[GraphEdgeRead]


class GraphNeighborhoodRead(GraphRead):
    center_node_id: str


class DocumentGraphRead(GraphRead):
    document_id: str
    chunk_count: int
    pending_candidate_count: int


CandidateKind = Literal["node", "relationship"]


class CandidateEvidenceRead(ApiModel):
    id: str
    document_id: str
    document_name: str
    document_type: DocumentType
    page: int | None = None
    section: str | None = None
    source_location: dict[str, Any]
    excerpt: str
    confidence: float
    created_at: datetime


class CandidateNodeRead(ApiModel):
    kind: Literal["node"] = "node"
    id: str
    course_id: str
    type: GraphNodeType
    label: str
    description: str | None
    confidence: float | None
    review_status: ReviewStatus
    review_note: str | None = None
    reviewed_at: datetime | None = None
    merged_into_node_id: str | None = None
    source_document_id: str | None
    source_document_name: str | None = None
    metadata: dict[str, Any]
    evidence_count: int
    created_at: datetime
    updated_at: datetime


class CandidateRelationshipRead(ApiModel):
    kind: Literal["relationship"] = "relationship"
    id: str
    course_id: str
    type: GraphEdgeType
    source_node_id: str
    target_node_id: str
    source_node_label: str | None
    target_node_label: str | None
    confidence: float | None
    review_status: ReviewStatus
    review_note: str | None = None
    reviewed_at: datetime | None = None
    merged_into_edge_id: str | None = None
    source_document_id: str | None
    source_document_name: str | None = None
    metadata: dict[str, Any]
    evidence_count: int
    created_at: datetime
    updated_at: datetime


class CandidateQueueRead(ApiModel):
    pending_count: int
    nodes: list[CandidateNodeRead]
    relationships: list[CandidateRelationshipRead]


class CandidateNodeDetailRead(ApiModel):
    candidate: CandidateNodeRead
    evidence: list[CandidateEvidenceRead]
    related_nodes: list[GraphNodeRead]


class CandidateRelationshipDetailRead(ApiModel):
    candidate: CandidateRelationshipRead
    evidence: list[CandidateEvidenceRead]
    related_nodes: list[GraphNodeRead]


class CandidateNodeEdit(ApiModel):
    type: GraphNodeType | None = None
    label: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, Any] | None = None

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def validate_edit(self) -> "CandidateNodeEdit":
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class CandidateRelationshipEdit(ApiModel):
    type: GraphEdgeType | None = None
    source_node_id: str | None = None
    target_node_id: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_edit(self) -> "CandidateRelationshipEdit":
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class ReviewDecision(ApiModel):
    note: str | None = Field(default=None, max_length=2_000)


class CandidateMerge(ApiModel):
    target_id: str = Field(min_length=1)
    note: str | None = Field(default=None, max_length=2_000)


class BulkApproveRequest(ApiModel):
    node_ids: list[str] = Field(default_factory=list)
    relationship_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_selection(self) -> "BulkApproveRequest":
        if not self.node_ids and not self.relationship_ids:
            raise ValueError("select at least one candidate")
        if len(self.node_ids) + len(self.relationship_ids) > 100:
            raise ValueError("approve at most 100 candidates at a time")
        return self


class BulkApproveFailure(ApiModel):
    id: str
    kind: CandidateKind
    reason: str


class BulkApproveResult(ApiModel):
    approved_node_ids: list[str]
    approved_relationship_ids: list[str]
    failures: list[BulkApproveFailure]


class CandidateMergeResult(ApiModel):
    candidate_id: str
    kind: CandidateKind
    target_node: GraphNodeRead | None = None
    target_relationship: GraphEdgeRead | None = None
