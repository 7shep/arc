from typing import Any, Protocol

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Course,
    Document,
    GraphEdge,
    GraphEdgeType,
    GraphNode,
    GraphNodeType,
    utcnow,
)


class GraphRecordNotFound(Exception):
    pass


class InvalidGraphReference(Exception):
    pass


class DuplicateGraphRecord(Exception):
    pass


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
                .where(GraphNode.course_id == course_id, GraphNode.archived_at.is_(None))
                .order_by(GraphNode.created_at, GraphNode.id)
            ).all()
        )
        relationships = list(
            self.db.scalars(
                select(GraphEdge)
                .where(GraphEdge.course_id == course_id, GraphEdge.archived_at.is_(None))
                .order_by(GraphEdge.created_at, GraphEdge.id)
            ).all()
        )
        return nodes, relationships

    def get_counts(self, course_id: str) -> tuple[int, int]:
        self.ensure_course(course_id)
        node_count = self.db.scalar(
            select(func.count(GraphNode.id)).where(
                GraphNode.course_id == course_id, GraphNode.archived_at.is_(None)
            )
        ) or 0
        relationship_count = self.db.scalar(
            select(func.count(GraphEdge.id)).where(
                GraphEdge.course_id == course_id, GraphEdge.archived_at.is_(None)
            )
        ) or 0
        return node_count, relationship_count
