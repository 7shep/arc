from collections.abc import Callable
from functools import wraps
from typing import Annotated, Any, Literal
from uuid import UUID

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.documents.service import (
    CourseNotFoundError,
    DocumentContentUnavailableError,
    DocumentNotFoundError,
    DocumentService,
)
from app.graph.service import CourseGraph, GraphValidationError, SqlCourseGraph
from app.mcp.schemas import (
    CandidateNodeResult,
    CandidateRelationshipResult,
    DocumentChunksResult,
    DocumentListResult,
    DocumentResult,
    DocumentStatusResult,
    EvidenceResult,
    SourceLocation,
)
from app.models import GraphEdgeType, GraphNodeType, ReviewStatus
from app.storage.base import StorageProvider
from app.storage.local import LocalStorageProvider

SessionFactory = Callable[[], Session]
StorageFactory = Callable[[], StorageProvider]
GraphFactory = Callable[[Session], CourseGraph]
EXPECTED_TOOL_ERRORS = (
    CourseNotFoundError,
    DocumentContentUnavailableError,
    DocumentNotFoundError,
    GraphValidationError,
)


def _handle_tool_errors(function: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except EXPECTED_TOOL_ERRORS as error:
            raise ToolError(str(error)) from error

    return wrapped


def _default_storage() -> StorageProvider:
    return LocalStorageProvider(get_settings().upload_dir)


def _document_result(document: Any) -> DocumentResult:
    return DocumentResult.model_validate(document, from_attributes=True)


def _evidence_result(evidence: Any, target_type: Literal["node", "relationship"]) -> EvidenceResult:
    target_id = evidence.graph_node_id or evidence.graph_edge_id
    return EvidenceResult(
        id=evidence.id,
        target_type=target_type,
        target_id=target_id,
        document_id=evidence.document_id,
        source_location=evidence.source_location,
        excerpt=evidence.excerpt,
        confidence=evidence.confidence,
    )


def create_mcp_server(
    session_factory: SessionFactory = SessionLocal,
    storage_factory: StorageFactory = _default_storage,
    graph_factory: GraphFactory = SqlCourseGraph,
) -> MCPServer:
    server = MCPServer(
        "Arc Course Graph Extraction",
        version="0.1.0",
        instructions=(
            "Extract only evidence-supported candidate graph records. "
            "Candidates require human review and are never approved by these tools."
        ),
    )

    @server.tool()
    @_handle_tool_errors
    def list_course_documents(
        course_id: UUID, include_processed: bool = False
    ) -> DocumentListResult:
        """List uploaded/unprocessed course documents, optionally including processed sources."""
        with session_factory() as db:
            documents = DocumentService(db, storage_factory()).list_documents(
                str(course_id), include_processed=include_processed
            )
            return DocumentListResult(documents=[_document_result(item) for item in documents])

    @server.tool()
    @_handle_tool_errors
    def get_document_metadata(course_id: UUID, document_id: UUID) -> DocumentResult:
        """Retrieve metadata for one document, scoped to its course."""
        with session_factory() as db:
            document = DocumentService(db, storage_factory()).get_document(
                str(course_id), str(document_id)
            )
            return _document_result(document)

    @server.tool()
    @_handle_tool_errors
    def get_document_chunks(
        course_id: UUID,
        document_id: UUID,
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=100)] = 50,
    ) -> DocumentChunksResult:
        """Retrieve ordered document text chunks with source-aware locations."""
        if offset < 0:
            raise ToolError("offset must be at least 0")
        if not 1 <= limit <= 100:
            raise ToolError("limit must be between 1 and 100")
        with session_factory() as db:
            service = DocumentService(db, storage_factory())
            chunks = service.get_chunks(
                str(course_id), str(document_id), offset=offset, limit=limit
            )
            db.commit()
            return DocumentChunksResult.model_validate(
                {"chunks": chunks}, from_attributes=True
            )

    @server.tool()
    @_handle_tool_errors
    def create_candidate_node(
        course_id: UUID,
        node_type: GraphNodeType,
        label: Annotated[str, Field(min_length=1, max_length=255)],
        document_id: UUID,
        source_location: SourceLocation,
        excerpt: Annotated[str, Field(min_length=1, max_length=4_000)],
        confidence: Annotated[float, Field(ge=0, le=1)],
        description: Annotated[str | None, Field(max_length=10_000)] = None,
        metadata: dict[str, Any] | None = None,
    ) -> CandidateNodeResult:
        """Create an evidence-backed candidate node that remains pending human review."""
        label = label.strip()
        excerpt = excerpt.strip()
        if not label or len(label) > 255:
            raise ToolError("label must contain 1 to 255 characters")
        if description is not None and len(description) > 10_000:
            raise ToolError("description must be at most 10000 characters")
        if not excerpt or len(excerpt) > 4_000:
            raise ToolError("excerpt must contain 1 to 4000 characters")
        if not 0 <= confidence <= 1:
            raise ToolError("confidence must be between 0 and 1")
        location = source_location.model_dump(exclude_none=True)
        with session_factory() as db:
            documents = DocumentService(db, storage_factory())
            documents.get_document(str(course_id), str(document_id))
            graph = graph_factory(db)
            node = graph.create_node(
                str(course_id),
                node_type,
                label,
                description=description,
                confidence=confidence,
                review_status=ReviewStatus.CANDIDATE,
                node_metadata=metadata or {},
            )
            evidence = graph.attach_evidence(
                str(course_id),
                "node",
                node.id,
                str(document_id),
                location,
                excerpt,
                confidence,
            )
            db.commit()
            return CandidateNodeResult(
                id=node.id,
                course_id=node.course_id,
                node_type=node.type,
                label=node.label,
                description=node.description,
                review_status=node.review_status,
                confidence=node.confidence,
                evidence=_evidence_result(evidence, "node"),
            )

    @server.tool()
    @_handle_tool_errors
    def create_candidate_relationship(
        course_id: UUID,
        source_node_id: UUID,
        target_node_id: UUID,
        relationship_type: GraphEdgeType,
        document_id: UUID,
        source_location: SourceLocation,
        excerpt: Annotated[str, Field(min_length=1, max_length=4_000)],
        confidence: Annotated[float, Field(ge=0, le=1)],
        metadata: dict[str, Any] | None = None,
    ) -> CandidateRelationshipResult:
        """Create an evidence-backed candidate relationship pending human review."""
        excerpt = excerpt.strip()
        if not excerpt or len(excerpt) > 4_000:
            raise ToolError("excerpt must contain 1 to 4000 characters")
        if not 0 <= confidence <= 1:
            raise ToolError("confidence must be between 0 and 1")
        location = source_location.model_dump(exclude_none=True)
        with session_factory() as db:
            graph = graph_factory(db)
            edge = graph.create_edge(
                str(course_id),
                str(source_node_id),
                str(target_node_id),
                relationship_type,
                confidence=confidence,
                review_status=ReviewStatus.CANDIDATE,
                edge_metadata=metadata or {},
            )
            evidence = graph.attach_evidence(
                str(course_id),
                "relationship",
                edge.id,
                str(document_id),
                location,
                excerpt,
                confidence,
            )
            db.commit()
            return CandidateRelationshipResult(
                id=edge.id,
                course_id=edge.course_id,
                source_node_id=edge.source_node_id,
                target_node_id=edge.target_node_id,
                relationship_type=edge.type,
                review_status=edge.review_status,
                confidence=edge.confidence,
                evidence=_evidence_result(evidence, "relationship"),
            )

    @server.tool()
    @_handle_tool_errors
    def attach_source_evidence(
        course_id: UUID,
        target_type: Literal["node", "relationship"],
        target_id: UUID,
        document_id: UUID,
        source_location: SourceLocation,
        excerpt: Annotated[str, Field(min_length=1, max_length=4_000)],
        confidence: Annotated[float, Field(ge=0, le=1)],
    ) -> EvidenceResult:
        """Attach another source citation and confidence score to a candidate graph record."""
        excerpt = excerpt.strip()
        if not excerpt or len(excerpt) > 4_000:
            raise ToolError("excerpt must contain 1 to 4000 characters")
        if not 0 <= confidence <= 1:
            raise ToolError("confidence must be between 0 and 1")
        with session_factory() as db:
            graph = graph_factory(db)
            target = (
                graph.find_node(str(target_id))
                if target_type == "node"
                else graph.find_edge(str(target_id))
            )
            if target is None or target.course_id != str(course_id):
                raise GraphValidationError(f"Evidence {target_type} not found in course")
            if target.review_status != ReviewStatus.CANDIDATE:
                raise GraphValidationError("Evidence can only be attached to candidate records")
            evidence = graph.attach_evidence(
                str(course_id),
                target_type,
                str(target_id),
                str(document_id),
                source_location.model_dump(exclude_none=True),
                excerpt,
                confidence,
            )
            db.commit()
            return _evidence_result(evidence, target_type)

    @server.tool()
    @_handle_tool_errors
    def mark_document_processed(course_id: UUID, document_id: UUID) -> DocumentStatusResult:
        """Mark a course document as successfully processed."""
        with session_factory() as db:
            document = DocumentService(db, storage_factory()).mark_processed(
                str(course_id), str(document_id)
            )
            db.commit()
            return DocumentStatusResult(
                document_id=document.id,
                processing_status=document.processing_status,
                processing_error=document.processing_error,
            )

    @server.tool()
    @_handle_tool_errors
    def report_document_processing_failure(
        course_id: UUID,
        document_id: UUID,
        reason: Annotated[str, Field(min_length=1, max_length=2_000)],
    ) -> DocumentStatusResult:
        """Record a course-scoped document processing failure and actionable reason."""
        reason = reason.strip()
        if not reason or len(reason) > 2_000:
            raise ToolError("reason must contain 1 to 2000 characters")
        with session_factory() as db:
            document = DocumentService(db, storage_factory()).report_failure(
                str(course_id), str(document_id), reason
            )
            db.commit()
            return DocumentStatusResult(
                document_id=document.id,
                processing_status=document.processing_status,
                processing_error=document.processing_error,
            )

    return server


mcp = create_mcp_server()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
