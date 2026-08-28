from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.graph.service import SqlCourseGraph
from app.migrate import migrate
from app.models import Course, GraphEdgeType, GraphNodeType


def seed() -> None:
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        for name in migrate(engine):
            print(f"Applied migration: {name}")
    with SessionLocal() as db:
        existing = db.scalar(select(Course).where(Course.code == "MATH221"))
        if existing:
            print(f"Seed already present: {existing.id}")
            return
        course = Course(
            name="Vector Calculus",
            code="MATH221",
            description="A connected workspace for multivariable calculus.",
        )
        db.add(course)
        db.flush()
        graph = SqlCourseGraph(db)
        nodes = {
            label: graph.create_node(course.id, node_type, label)
            for label, node_type in [
                ("Vectors", GraphNodeType.CONCEPT),
                ("Vector Fields", GraphNodeType.CONCEPT),
                ("Line Integrals", GraphNodeType.CONCEPT),
                ("Green's Theorem", GraphNodeType.CONCEPT),
                ("Lecture 05", GraphNodeType.LECTURE),
                ("Lecture 07", GraphNodeType.LECTURE),
                ("Assignment 03", GraphNodeType.ASSIGNMENT),
            ]
        }
        for source, target, edge_type in [
            ("Vector Fields", "Vectors", GraphEdgeType.REQUIRES),
            ("Line Integrals", "Vector Fields", GraphEdgeType.REQUIRES),
            ("Green's Theorem", "Line Integrals", GraphEdgeType.REQUIRES),
            ("Line Integrals", "Lecture 05", GraphEdgeType.TAUGHT_IN),
            ("Green's Theorem", "Lecture 07", GraphEdgeType.TAUGHT_IN),
            ("Green's Theorem", "Assignment 03", GraphEdgeType.APPEARS_IN),
        ]:
            graph.create_edge(course.id, nodes[source].id, nodes[target].id, edge_type)
        db.commit()
        print(f"Seeded MATH221: {course.id}")


if __name__ == "__main__":
    seed()
