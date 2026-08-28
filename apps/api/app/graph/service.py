import json
from typing import Any, Literal, Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    Course,
    Document,
    GraphEdge,
    GraphEdgeType,
    GraphEvidence,
    GraphNode,
    GraphNodeType,
)


class GraphValidationError(ValueError):
    pass


class CourseGraph(Protocol):
    def create_node(
        self, course_id: str, node_type: GraphNodeType, label: str, **kwargs: Any
    ) -> GraphNode: ...
    def create_edge(
        self,
        course_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_type: GraphEdgeType,
        **kwargs: Any,
    ) -> GraphEdge: ...
    def get_node(self, node_id: str) -> GraphNode | None: ...
    def get_edge(self, edge_id: str) -> GraphEdge | None: ...
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
    def get_neighbors(self, node_id: str) -> list[GraphNode]: ...
    def search_nodes(self, course_id: str, query: str) -> list[GraphNode]: ...


class SqlCourseGraph:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_node(
        self, course_id: str, node_type: GraphNodeType, label: str, **kwargs: Any
    ) -> GraphNode:
        if self.db.get(Course, course_id) is None:
            raise GraphValidationError("Course not found")
        node = GraphNode(course_id=course_id, type=node_type, label=label, **kwargs)
        self.db.add(node)
        self.db.flush()
        return node

    def create_edge(
        self,
        course_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_type: GraphEdgeType,
        **kwargs: Any,
    ) -> GraphEdge:
        if source_node_id == target_node_id:
            raise GraphValidationError("A relationship cannot connect a node to itself")
        source = self.get_node(source_node_id)
        target = self.get_node(target_node_id)
        if source is None or target is None:
            raise GraphValidationError("Source or target node not found")
        if source.course_id != course_id or target.course_id != course_id:
            raise GraphValidationError("Source and target nodes must belong to the course")
        edge = GraphEdge(
            course_id=course_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            type=edge_type,
            **kwargs,
        )
        self.db.add(edge)
        self.db.flush()
        return edge

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.db.get(GraphNode, node_id)

    def get_edge(self, edge_id: str) -> GraphEdge | None:
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
        node = self.get_node(target_id) if target_type == "node" else None
        edge = self.get_edge(target_id) if target_type == "relationship" else None
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

    def get_neighbors(self, node_id: str) -> list[GraphNode]:
        edges = self.db.scalars(
            select(GraphEdge).where(
                or_(GraphEdge.source_node_id == node_id, GraphEdge.target_node_id == node_id)
            )
        ).all()
        ids = {
            edge.target_node_id if edge.source_node_id == node_id else edge.source_node_id
            for edge in edges
        }
        return (
            list(self.db.scalars(select(GraphNode).where(GraphNode.id.in_(ids))).all())
            if ids
            else []
        )

    def search_nodes(self, course_id: str, query: str) -> list[GraphNode]:
        return list(
            self.db.scalars(
                select(GraphNode)
                .where(GraphNode.course_id == course_id, GraphNode.label.ilike(f"%{query}%"))
                .limit(25)
            ).all()
        )
