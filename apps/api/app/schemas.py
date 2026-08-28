from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    metadata: dict[str, Any] = Field(validation_alias="node_metadata")
    created_at: datetime
    updated_at: datetime


class GraphEdgeRead(ApiModel):
    id: str
    course_id: str
    source_node_id: str
    target_node_id: str
    type: GraphEdgeType
    confidence: float | None
    metadata: dict[str, Any] = Field(validation_alias="edge_metadata")
    created_at: datetime


class GraphRead(ApiModel):
    nodes: list[GraphNodeRead]
    edges: list[GraphEdgeRead]
