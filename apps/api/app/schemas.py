from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import DocumentType, GraphEdgeType, GraphNodeType, ProcessingStatus


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
