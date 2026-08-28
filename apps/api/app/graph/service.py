from typing import Any, Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import GraphEdge, GraphEdgeType, GraphNode, GraphNodeType


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
    def get_neighbors(self, node_id: str) -> list[GraphNode]: ...
    def search_nodes(self, course_id: str, query: str) -> list[GraphNode]: ...


class SqlCourseGraph:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_node(
        self, course_id: str, node_type: GraphNodeType, label: str, **kwargs: Any
    ) -> GraphNode:
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
