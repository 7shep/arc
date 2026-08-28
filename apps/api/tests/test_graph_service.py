from sqlalchemy.orm import Session

from app.database import engine
from app.graph.service import SqlCourseGraph
from app.models import Course, GraphEdgeType, GraphNodeType


def test_graph_contract_create_search_and_neighbors() -> None:
    with Session(engine) as db:
        course = Course(name="Algorithms", code="CS300")
        db.add(course)
        db.flush()
        graph = SqlCourseGraph(db)
        trees = graph.create_node(course.id, GraphNodeType.CONCEPT, "Trees")
        graphs = graph.create_node(course.id, GraphNodeType.CONCEPT, "Graphs")
        graph.create_edge(course.id, graphs.id, trees.id, GraphEdgeType.REQUIRES)
        db.commit()
        assert graph.get_node(trees.id).label == "Trees"
        assert [node.label for node in graph.get_neighbors(graphs.id)] == ["Trees"]
        assert [node.label for node in graph.search_nodes(course.id, "graph")] == ["Graphs"]
