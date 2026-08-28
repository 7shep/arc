from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Course, GraphEdge, GraphNode
from app.schemas import GraphRead

router = APIRouter(prefix="/courses/{course_id}/graph", tags=["graph"])


@router.get("", response_model=GraphRead)
def get_graph(course_id: str, db: Session = Depends(get_db)) -> GraphRead:
    if not db.get(Course, course_id):
        raise HTTPException(status_code=404, detail="Course not found")
    nodes = db.scalars(select(GraphNode).where(GraphNode.course_id == course_id)).all()
    edges = db.scalars(select(GraphEdge).where(GraphEdge.course_id == course_id)).all()
    return GraphRead.model_validate({"nodes": nodes, "edges": edges})
