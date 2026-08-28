import json
from collections.abc import Collection
from typing import Any, Literal, Protocol

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    APPROVED_REVIEW_STATUSES,
    REVIEWABLE_STATUSES,
    Course,
    Document,
    GraphEdge,
    GraphEdgeType,
    GraphEvidence,
    GraphNode,
    GraphNodeType,
    ReviewStatus,
    utcnow,
)


class GraphValidationError(ValueError):
    pass


class GraphRecordNotFound(GraphValidationError):
    pass


class InvalidGraphReference(GraphValidationError):
    pass


class DuplicateGraphRecord(GraphValidationError):
    pass


class InvalidReviewTransition(GraphValidationError):
    """Raised when a review action does not apply to a record's current review status."""


class CourseGraph(Protocol):
    def ensure_course(self, course_id: str) -> None: ...
    def create_node(
        self, course_id: str, node_type: GraphNodeType, label: str, **kwargs: Any
    ) -> GraphNode: ...
    def update_node(self, course_id: str, node_id: str, values: dict[str, Any]) -> GraphNode: ...
    def get_node(self, course_id: str, node_id: str) -> GraphNode: ...
    def archive_node(self, course_id: str, node_id: str) -> None: ...
    def create_relationship(
        self,
        course_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_type: GraphEdgeType,
        **kwargs: Any,
    ) -> GraphEdge: ...
    def create_edge(
        self,
        course_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_type: GraphEdgeType,
        **kwargs: Any,
    ) -> GraphEdge: ...
    def find_node(self, node_id: str) -> GraphNode | None: ...
    def find_edge(self, edge_id: str) -> GraphEdge | None: ...
    def attach_evidence(
        self,
        course_id: str,
        target_type: Literal["node", "relationship"],
        target_id: str,
        document_id: str,
        source_location: dict[str, Any],
        excerpt: str,
        confidence: float,
    ) -> GraphEvidence: ...
    def update_relationship(
        self, course_id: str, relationship_id: str, values: dict[str, Any]
    ) -> GraphEdge: ...
    def get_relationship(self, course_id: str, relationship_id: str) -> GraphEdge: ...
    def archive_relationship(self, course_id: str, relationship_id: str) -> None: ...
    def get_neighbors(
        self, course_id: str, node_id: str
    ) -> tuple[list[GraphNode], list[GraphEdge]]: ...
    def search_nodes(self, course_id: str, query: str, limit: int = 25) -> list[GraphNode]: ...
    def get_visualization(self, course_id: str) -> tuple[list[GraphNode], list[GraphEdge]]: ...
    def get_counts(self, course_id: str) -> tuple[int, int]: ...
    def list_candidate_nodes(
        self,
        course_id: str,
        *,
        statuses: Collection[ReviewStatus] | None = None,
        document_id: str | None = None,
    ) -> list[GraphNode]: ...
    def list_candidate_relationships(
        self,
        course_id: str,
        *,
        statuses: Collection[ReviewStatus] | None = None,
        document_id: str | None = None,
    ) -> list[GraphEdge]: ...
    def get_candidate_node(self, course_id: str, node_id: str) -> GraphNode: ...
    def find_approved_node_by_label(self, course_id: str, label: str) -> GraphNode | None: ...
    def match_approved_node(self, course_id: str, label: str) -> GraphNode | None: ...
    def find_approved_relationship(
        self, course_id: str, source_node_id: str, target_node_id: str, edge_type: GraphEdgeType
    ) -> GraphEdge | None: ...
    def get_candidate_relationship(self, course_id: str, relationship_id: str) -> GraphEdge: ...
    def list_evidence(
        self, course_id: str, target_type: Literal["node", "relationship"], target_id: str
    ) -> list[GraphEvidence]: ...
    def merge_node(self, course_id: str, candidate_id: str, target_id: str) -> GraphNode: ...
    def merge_relationship(
        self, course_id: str, candidate_id: str, target_id: str
    ) -> GraphEdge: ...
    def get_document_records(
        self, course_id: str, document_id: str
    ) -> tuple[list[GraphNode], list[GraphEdge]]: ...


class SqlCourseGraph:
    """Dialect-neutral SQL implementation used by both SQLite and PostgreSQL."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_course(self, course_id: str) -> None:
        if not self.db.get(Course, course_id):
            raise GraphRecordNotFound("Course not found")

    def _validate_source(self, course_id: str, document_id: str | None) -> None:
        if document_id is None:
            return
        document = self.db.get(Document, document_id)
        if not document or document.course_id != course_id:
            raise InvalidGraphReference("Source document does not belong to this course")

    def _active_node(self, course_id: str, node_id: str) -> GraphNode:
        node = self.db.scalar(
            select(GraphNode).where(
                GraphNode.id == node_id,
                GraphNode.course_id == course_id,
                GraphNode.archived_at.is_(None),
            )
        )
        if not node:
            raise GraphRecordNotFound("Graph node not found")
        return node

    def _active_relationship(self, course_id: str, relationship_id: str) -> GraphEdge:
        relationship = self.db.scalar(
            select(GraphEdge).where(
                GraphEdge.id == relationship_id,
                GraphEdge.course_id == course_id,
                GraphEdge.archived_at.is_(None),
            )
        )
        if not relationship:
            raise GraphRecordNotFound("Graph relationship not found")
        return relationship

    def _validate_node_reference(self, course_id: str, node_id: str) -> None:
        try:
            self._active_node(course_id, node_id)
        except GraphRecordNotFound as exc:
            raise InvalidGraphReference(
                "Relationship nodes must be active nodes in this course"
            ) from exc

    def _flush_unique(self, detail: str) -> None:
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateGraphRecord(detail) from exc

    def create_node(
        self, course_id: str, node_type: GraphNodeType, label: str, **kwargs: Any
    ) -> GraphNode:
        self.ensure_course(course_id)
        self._validate_source(course_id, kwargs.get("source_document_id"))
        node = GraphNode(course_id=course_id, type=node_type, label=label, **kwargs)
        self.db.add(node)
        self._flush_unique("A node with this label already exists in the course")
        return node

    def update_node(self, course_id: str, node_id: str, values: dict[str, Any]) -> GraphNode:
        node = self._active_node(course_id, node_id)
        source_document_id = values.get("source_document_id", node.source_document_id)
        source_location = values.get("source_location", node.source_location)
        if source_location and not source_document_id:
            raise InvalidGraphReference("sourceDocumentId is required for sourceLocation")
        self._validate_source(course_id, source_document_id)
        for key, value in values.items():
            setattr(node, "node_metadata" if key == "metadata" else key, value)
        self._flush_unique("A node with this label already exists in the course")
        return node

    def get_node(self, course_id: str, node_id: str) -> GraphNode:
        self.ensure_course(course_id)
        return self._active_node(course_id, node_id)

    def archive_node(self, course_id: str, node_id: str) -> None:
        node = self.get_node(course_id, node_id)
        archived_at = utcnow()
        node.archived_at = archived_at
        relationships = self.db.scalars(
            select(GraphEdge).where(
                GraphEdge.course_id == course_id,
                GraphEdge.archived_at.is_(None),
                or_(
                    GraphEdge.source_node_id == node_id,
                    GraphEdge.target_node_id == node_id,
                ),
            )
        ).all()
        for relationship in relationships:
            relationship.archived_at = archived_at
        self.db.flush()

    def create_relationship(
        self,
        course_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_type: GraphEdgeType,
        **kwargs: Any,
    ) -> GraphEdge:
        self.ensure_course(course_id)
        if source_node_id == target_node_id:
            raise InvalidGraphReference("A relationship cannot connect a node to itself")
        self._validate_node_reference(course_id, source_node_id)
        self._validate_node_reference(course_id, target_node_id)
        self._validate_source(course_id, kwargs.get("source_document_id"))
        relationship = GraphEdge(
            course_id=course_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            type=edge_type,
            **kwargs,
        )
        self.db.add(relationship)
        self._flush_unique("This relationship already exists")
        return relationship

    def create_edge(
        self,
        course_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_type: GraphEdgeType,
        **kwargs: Any,
    ) -> GraphEdge:
        """Backward-compatible name for ingestion callers using the original contract."""
        return self.create_relationship(
            course_id, source_node_id, target_node_id, edge_type, **kwargs
        )

    def update_relationship(
        self, course_id: str, relationship_id: str, values: dict[str, Any]
    ) -> GraphEdge:
        relationship = self._active_relationship(course_id, relationship_id)
        source_node_id = values.get("source_node_id", relationship.source_node_id)
        target_node_id = values.get("target_node_id", relationship.target_node_id)
        if source_node_id == target_node_id:
            raise InvalidGraphReference("A relationship cannot connect a node to itself")
        self._validate_node_reference(course_id, source_node_id)
        self._validate_node_reference(course_id, target_node_id)
        source_document_id = values.get(
            "source_document_id", relationship.source_document_id
        )
        source_location = values.get("source_location", relationship.source_location)
        if source_location and not source_document_id:
            raise InvalidGraphReference("sourceDocumentId is required for sourceLocation")
        self._validate_source(course_id, source_document_id)
        for key, value in values.items():
            setattr(relationship, "edge_metadata" if key == "metadata" else key, value)
        self._flush_unique("This relationship already exists")
        return relationship

    def get_relationship(self, course_id: str, relationship_id: str) -> GraphEdge:
        self.ensure_course(course_id)
        return self._active_relationship(course_id, relationship_id)

    def archive_relationship(self, course_id: str, relationship_id: str) -> None:
        relationship = self.get_relationship(course_id, relationship_id)
        relationship.archived_at = utcnow()
        self.db.flush()

    def find_node(self, node_id: str) -> GraphNode | None:
        return self.db.get(GraphNode, node_id)

    def find_edge(self, edge_id: str) -> GraphEdge | None:
        return self.db.get(GraphEdge, edge_id)

    def attach_evidence(
        self,
        course_id: str,
        target_type: Literal["node", "relationship"],
        target_id: str,
        document_id: str,
        source_location: dict[str, Any],
        excerpt: str,
        confidence: float,
    ) -> GraphEvidence:
        document = self.db.get(Document, document_id)
        if document is None or document.course_id != course_id:
            raise GraphValidationError("Evidence document not found in course")
        node = self.find_node(target_id) if target_type == "node" else None
        edge = self.find_edge(target_id) if target_type == "relationship" else None
        target = node or edge
        if target is None or target.course_id != course_id:
            raise GraphValidationError(f"Evidence {target_type} not found in course")
        evidence = GraphEvidence(
            course_id=course_id,
            graph_node_id=node.id if node else None,
            graph_edge_id=edge.id if edge else None,
            document_id=document_id,
            source_location=source_location,
            excerpt=excerpt,
            confidence=confidence,
        )
        target.confidence = confidence
        if node is not None and node.source_document_id is None:
            node.source_document_id = document_id
            node.source_location = json.dumps(source_location, separators=(",", ":"))[:255]
        self.db.add(evidence)
        self.db.flush()
        return evidence

    def get_neighbors(
        self, course_id: str, node_id: str
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        self.ensure_course(course_id)
        self._active_node(course_id, node_id)
        relationships = list(
            self.db.scalars(
                select(GraphEdge)
                .where(
                    GraphEdge.course_id == course_id,
                    GraphEdge.archived_at.is_(None),
                    GraphEdge.review_status.in_(APPROVED_REVIEW_STATUSES),
                    or_(
                        GraphEdge.source_node_id == node_id,
                        GraphEdge.target_node_id == node_id,
                    ),
                )
                .order_by(GraphEdge.created_at, GraphEdge.id)
            ).all()
        )
        neighbor_ids = {
            relationship.target_node_id
            if relationship.source_node_id == node_id
            else relationship.source_node_id
            for relationship in relationships
        }
        nodes = (
            list(
                self.db.scalars(
                    select(GraphNode)
                    .where(
                        GraphNode.course_id == course_id,
                        GraphNode.id.in_(neighbor_ids),
                        GraphNode.archived_at.is_(None),
                        GraphNode.review_status.in_(APPROVED_REVIEW_STATUSES),
                    )
                    .order_by(GraphNode.label, GraphNode.id)
                ).all()
            )
            if neighbor_ids
            else []
        )
        active_ids = {node.id for node in nodes}
        relationships = [
            relationship
            for relationship in relationships
            if (
                relationship.target_node_id
                if relationship.source_node_id == node_id
                else relationship.source_node_id
            )
            in active_ids
        ]
        return nodes, relationships

    def search_nodes(self, course_id: str, query: str, limit: int = 25) -> list[GraphNode]:
        self.ensure_course(course_id)
        pattern = f"%{query.strip()}%"
        return list(
            self.db.scalars(
                select(GraphNode)
                .where(
                    GraphNode.course_id == course_id,
                    GraphNode.archived_at.is_(None),
                    GraphNode.review_status.in_(APPROVED_REVIEW_STATUSES),
                    or_(GraphNode.label.ilike(pattern), GraphNode.description.ilike(pattern)),
                )
                .order_by(GraphNode.label, GraphNode.id)
                .limit(limit)
            ).all()
        )

    def get_visualization(self, course_id: str) -> tuple[list[GraphNode], list[GraphEdge]]:
        self.ensure_course(course_id)
        nodes = list(
            self.db.scalars(
                select(GraphNode)
                .where(
                    GraphNode.course_id == course_id,
                    GraphNode.archived_at.is_(None),
                    GraphNode.review_status.in_(APPROVED_REVIEW_STATUSES),
                )
                .order_by(GraphNode.created_at, GraphNode.id)
            ).all()
        )
        relationships = list(
            self.db.scalars(
                select(GraphEdge)
                .where(
                    GraphEdge.course_id == course_id,
                    GraphEdge.archived_at.is_(None),
                    GraphEdge.review_status.in_(APPROVED_REVIEW_STATUSES),
                )
                .order_by(GraphEdge.created_at, GraphEdge.id)
            ).all()
        )
        return nodes, relationships

    def get_counts(self, course_id: str) -> tuple[int, int]:
        self.ensure_course(course_id)
        node_count = self.db.scalar(
            select(func.count(GraphNode.id)).where(
                GraphNode.course_id == course_id,
                GraphNode.archived_at.is_(None),
                GraphNode.review_status.in_(APPROVED_REVIEW_STATUSES),
            )
        ) or 0
        relationship_count = self.db.scalar(
            select(func.count(GraphEdge.id)).where(
                GraphEdge.course_id == course_id,
                GraphEdge.archived_at.is_(None),
                GraphEdge.review_status.in_(APPROVED_REVIEW_STATUSES),
            )
        ) or 0
        return node_count, relationship_count

    # Review workflow support. Candidates live in the graph tables with a review status so
    # approval promotes an existing record instead of copying data between stores.

    def list_candidate_nodes(
        self,
        course_id: str,
        *,
        statuses: Collection[ReviewStatus] | None = None,
        document_id: str | None = None,
    ) -> list[GraphNode]:
        self.ensure_course(course_id)
        query = select(GraphNode).where(
            GraphNode.course_id == course_id,
            GraphNode.review_status.in_(tuple(statuses or REVIEWABLE_STATUSES)),
        )
        if document_id is not None:
            query = query.where(
                or_(
                    GraphNode.source_document_id == document_id,
                    GraphNode.id.in_(
                        select(GraphEvidence.graph_node_id).where(
                            GraphEvidence.document_id == document_id
                        )
                    ),
                )
            )
        return list(self.db.scalars(query.order_by(GraphNode.created_at, GraphNode.id)).all())

    def list_candidate_relationships(
        self,
        course_id: str,
        *,
        statuses: Collection[ReviewStatus] | None = None,
        document_id: str | None = None,
    ) -> list[GraphEdge]:
        self.ensure_course(course_id)
        query = select(GraphEdge).where(
            GraphEdge.course_id == course_id,
            GraphEdge.review_status.in_(tuple(statuses or REVIEWABLE_STATUSES)),
        )
        if document_id is not None:
            query = query.where(
                or_(
                    GraphEdge.source_document_id == document_id,
                    GraphEdge.id.in_(
                        select(GraphEvidence.graph_edge_id).where(
                            GraphEvidence.document_id == document_id
                        )
                    ),
                )
            )
        return list(self.db.scalars(query.order_by(GraphEdge.created_at, GraphEdge.id)).all())

    def get_candidate_node(self, course_id: str, node_id: str) -> GraphNode:
        """Return a node in any review status, including rejected and merged history."""
        self.ensure_course(course_id)
        node = self.db.scalar(
            select(GraphNode).where(GraphNode.id == node_id, GraphNode.course_id == course_id)
        )
        if not node:
            raise GraphRecordNotFound("Graph node not found")
        return node

    def get_candidate_relationship(self, course_id: str, relationship_id: str) -> GraphEdge:
        self.ensure_course(course_id)
        relationship = self.db.scalar(
            select(GraphEdge).where(
                GraphEdge.id == relationship_id, GraphEdge.course_id == course_id
            )
        )
        if not relationship:
            raise GraphRecordNotFound("Graph relationship not found")
        return relationship

    def list_evidence(
        self, course_id: str, target_type: Literal["node", "relationship"], target_id: str
    ) -> list[GraphEvidence]:
        column = (
            GraphEvidence.graph_node_id if target_type == "node" else GraphEvidence.graph_edge_id
        )
        return list(
            self.db.scalars(
                select(GraphEvidence)
                .where(GraphEvidence.course_id == course_id, column == target_id)
                .order_by(GraphEvidence.created_at, GraphEvidence.id)
            ).all()
        )

    def _record_merge_provenance(
        self, target: GraphNode | GraphEdge, candidate: GraphNode | GraphEdge
    ) -> None:
        attribute = "node_metadata" if isinstance(target, GraphNode) else "edge_metadata"
        candidate_attribute = (
            "node_metadata" if isinstance(candidate, GraphNode) else "edge_metadata"
        )
        metadata = dict(getattr(target, attribute) or {})
        provenance = dict(metadata.get("provenance") or {})
        merged = list(provenance.get("mergedCandidates") or [])
        entry: dict[str, Any] = {
            "candidateId": candidate.id,
            "mergedAt": utcnow().isoformat(),
            "metadata": getattr(candidate, candidate_attribute) or {},
        }
        if isinstance(candidate, GraphNode):
            entry["label"] = candidate.label
        if candidate.confidence is not None:
            entry["confidence"] = candidate.confidence
        if candidate.source_document_id:
            entry["sourceDocumentId"] = candidate.source_document_id
        merged.append(entry)
        provenance["mergedCandidates"] = merged
        metadata["provenance"] = provenance
        setattr(target, attribute, metadata)

    def _evidence_for_target(
        self, target_type: Literal["node", "relationship"], target_id: str
    ) -> list[GraphEvidence]:
        column = (
            GraphEvidence.graph_node_id if target_type == "node" else GraphEvidence.graph_edge_id
        )
        return list(self.db.scalars(select(GraphEvidence).where(column == target_id)).all())

    def _move_evidence(
        self, target_type: Literal["node", "relationship"], from_id: str, to_id: str
    ) -> None:
        for evidence in self._evidence_for_target(target_type, from_id):
            if target_type == "node":
                evidence.graph_node_id = to_id
            else:
                evidence.graph_edge_id = to_id

    def _approved_node(self, course_id: str, node_id: str) -> GraphNode:
        node = self.db.scalar(
            select(GraphNode).where(
                GraphNode.id == node_id,
                GraphNode.course_id == course_id,
                GraphNode.archived_at.is_(None),
                GraphNode.review_status.in_(APPROVED_REVIEW_STATUSES),
            )
        )
        if not node:
            raise InvalidGraphReference("Merge target must be an approved node in this course")
        return node

    def merge_node(self, course_id: str, candidate_id: str, target_id: str) -> GraphNode:
        """Fold a candidate node into an approved node, keeping every piece of provenance."""
        self.ensure_course(course_id)
        if candidate_id == target_id:
            raise InvalidGraphReference("A candidate cannot be merged into itself")
        candidate = self.get_candidate_node(course_id, candidate_id)
        target = self._approved_node(course_id, target_id)
        if not target.description and candidate.description:
            target.description = candidate.description
        if candidate.confidence is not None:
            target.confidence = max(target.confidence or 0.0, candidate.confidence)
        if target.source_document_id is None and candidate.source_document_id:
            target.source_document_id = candidate.source_document_id
            target.source_location = candidate.source_location
        self._move_evidence("node", candidate_id, target_id)
        self._record_merge_provenance(target, candidate)
        self._repoint_relationships(course_id, candidate_id, target_id)
        merged_at = utcnow()
        candidate.review_status = ReviewStatus.MERGED
        candidate.merged_into_node_id = target_id
        candidate.reviewed_at = merged_at
        candidate.archived_at = merged_at
        self.db.flush()
        return target

    def _repoint_relationships(self, course_id: str, candidate_id: str, target_id: str) -> None:
        """Move a merged node's relationships onto the target without creating duplicates."""
        relationships = self.db.scalars(
            select(GraphEdge).where(
                GraphEdge.course_id == course_id,
                GraphEdge.archived_at.is_(None),
                or_(
                    GraphEdge.source_node_id == candidate_id,
                    GraphEdge.target_node_id == candidate_id,
                ),
            )
        ).all()
        for relationship in relationships:
            merged_at = utcnow()
            source_node_id = (
                target_id
                if relationship.source_node_id == candidate_id
                else relationship.source_node_id
            )
            target_node_id = (
                target_id
                if relationship.target_node_id == candidate_id
                else relationship.target_node_id
            )
            if source_node_id == target_node_id:
                relationship.review_status = ReviewStatus.MERGED
                relationship.reviewed_at = merged_at
                relationship.archived_at = merged_at
                continue
            duplicate = self.db.scalar(
                select(GraphEdge).where(
                    GraphEdge.course_id == course_id,
                    GraphEdge.id != relationship.id,
                    GraphEdge.archived_at.is_(None),
                    GraphEdge.source_node_id == source_node_id,
                    GraphEdge.target_node_id == target_node_id,
                    GraphEdge.type == relationship.type,
                )
            )
            if duplicate is not None:
                self._move_evidence("relationship", relationship.id, duplicate.id)
                self._record_merge_provenance(duplicate, relationship)
                relationship.review_status = ReviewStatus.MERGED
                relationship.merged_into_edge_id = duplicate.id
                relationship.reviewed_at = merged_at
                relationship.archived_at = merged_at
                continue
            relationship.source_node_id = source_node_id
            relationship.target_node_id = target_node_id
        self.db.flush()

    def merge_relationship(self, course_id: str, candidate_id: str, target_id: str) -> GraphEdge:
        self.ensure_course(course_id)
        if candidate_id == target_id:
            raise InvalidGraphReference("A candidate cannot be merged into itself")
        candidate = self.get_candidate_relationship(course_id, candidate_id)
        target = self.db.scalar(
            select(GraphEdge).where(
                GraphEdge.id == target_id,
                GraphEdge.course_id == course_id,
                GraphEdge.archived_at.is_(None),
                GraphEdge.review_status.in_(APPROVED_REVIEW_STATUSES),
            )
        )
        if target is None:
            raise InvalidGraphReference(
                "Merge target must be an approved relationship in this course"
            )
        if candidate.confidence is not None:
            target.confidence = max(target.confidence or 0.0, candidate.confidence)
        if target.source_document_id is None and candidate.source_document_id:
            target.source_document_id = candidate.source_document_id
            target.source_location = candidate.source_location
        self._move_evidence("relationship", candidate_id, target_id)
        self._record_merge_provenance(target, candidate)
        merged_at = utcnow()
        candidate.review_status = ReviewStatus.MERGED
        candidate.merged_into_edge_id = target_id
        candidate.reviewed_at = merged_at
        candidate.archived_at = merged_at
        self.db.flush()
        return target

    def find_approved_node_by_label(self, course_id: str, label: str) -> GraphNode | None:
        return self.db.scalar(
            select(GraphNode).where(
                GraphNode.course_id == course_id,
                GraphNode.label == label,
                GraphNode.archived_at.is_(None),
                GraphNode.review_status.in_(APPROVED_REVIEW_STATUSES),
            )
        )

    def find_approved_relationship(
        self, course_id: str, source_node_id: str, target_node_id: str, edge_type: GraphEdgeType
    ) -> GraphEdge | None:
        return self.db.scalar(
            select(GraphEdge).where(
                GraphEdge.course_id == course_id,
                GraphEdge.source_node_id == source_node_id,
                GraphEdge.target_node_id == target_node_id,
                GraphEdge.type == edge_type,
                GraphEdge.archived_at.is_(None),
                GraphEdge.review_status.in_(APPROVED_REVIEW_STATUSES),
            )
        )

    def get_document_records(
        self, course_id: str, document_id: str
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        """Return the approved graph records that a document is the evidence for."""
        self.ensure_course(course_id)
        node_ids = select(GraphEvidence.graph_node_id).where(
            GraphEvidence.course_id == course_id, GraphEvidence.document_id == document_id
        )
        edge_ids = select(GraphEvidence.graph_edge_id).where(
            GraphEvidence.course_id == course_id, GraphEvidence.document_id == document_id
        )
        nodes = list(
            self.db.scalars(
                select(GraphNode)
                .where(
                    GraphNode.course_id == course_id,
                    GraphNode.archived_at.is_(None),
                    GraphNode.review_status.in_(APPROVED_REVIEW_STATUSES),
                    or_(
                        GraphNode.id.in_(node_ids),
                        GraphNode.source_document_id == document_id,
                    ),
                )
                .order_by(GraphNode.created_at, GraphNode.id)
            ).all()
        )
        relationships = list(
            self.db.scalars(
                select(GraphEdge)
                .where(
                    GraphEdge.course_id == course_id,
                    GraphEdge.archived_at.is_(None),
                    GraphEdge.review_status.in_(APPROVED_REVIEW_STATUSES),
                    or_(
                        GraphEdge.id.in_(edge_ids),
                        GraphEdge.source_document_id == document_id,
                    ),
                )
                .order_by(GraphEdge.created_at, GraphEdge.id)
            ).all()
        )
        return nodes, relationships

    def match_approved_node(self, course_id: str, label: str) -> GraphNode | None:
        """Case-insensitive label lookup used to fold re-extracted concepts into one node."""
        return self.db.scalars(
            select(GraphNode)
            .where(
                GraphNode.course_id == course_id,
                func.lower(GraphNode.label) == label.strip().lower(),
                GraphNode.archived_at.is_(None),
                GraphNode.review_status.in_(APPROVED_REVIEW_STATUSES),
            )
            .order_by(GraphNode.created_at)
        ).first()
