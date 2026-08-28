import pytest
from sqlalchemy.orm import Session

from app.database import engine
from app.graph.service import GraphRecordNotFound, SqlCourseGraph
from app.models import Course, GraphEdgeType, GraphNodeType


def test_graph_contract_create_update_search_neighbors_and_archive() -> None:
    with Session(engine) as db:
        course = Course(name="Algorithms", code="CS300")
        db.add(course)
        db.flush()
        graph = SqlCourseGraph(db)
        trees = graph.create_node(course.id, GraphNodeType.CONCEPT, "Trees")
        graphs = graph.create_node(
            course.id,
            GraphNodeType.CONCEPT,
            "Graphs",
            description="Graph structures",
        )
        relationship = graph.create_edge(
            course.id, graphs.id, trees.id, GraphEdgeType.REQUIRES
        )
        graph.update_node(course.id, trees.id, {"description": "Connected acyclic graphs"})
        graph.update_relationship(course.id, relationship.id, {"confidence": 0.9})
        db.commit()

        assert graph.get_node(course.id, trees.id).description == "Connected acyclic graphs"
        assert graph.get_relationship(course.id, relationship.id).confidence == 0.9
        neighbors, relationships = graph.get_neighbors(course.id, graphs.id)
        assert [node.label for node in neighbors] == ["Trees"]
        assert [item.id for item in relationships] == [relationship.id]
        assert [node.label for node in graph.search_nodes(course.id, "structure")] == [
            "Graphs"
        ]

        graph.archive_node(course.id, trees.id)
        db.commit()
        with pytest.raises(GraphRecordNotFound):
            graph.get_node(course.id, trees.id)
        assert graph.get_visualization(course.id) == ([graphs], [])


def test_sql_implementation_runs_on_supported_database_configuration() -> None:
    assert engine.dialect.name in {"sqlite", "postgresql"}
