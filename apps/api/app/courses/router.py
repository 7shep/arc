from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Course, Document, GraphEdge, GraphNode
from app.schemas import CourseCreate, CourseRead

router = APIRouter(prefix="/courses", tags=["courses"])


def course_read(db: Session, course: Course) -> CourseRead:
    document_count = (
        db.scalar(select(func.count(Document.id)).where(Document.course_id == course.id)) or 0
    )
    node_count = (
        db.scalar(select(func.count(GraphNode.id)).where(GraphNode.course_id == course.id)) or 0
    )
    edge_count = (
        db.scalar(select(func.count(GraphEdge.id)).where(GraphEdge.course_id == course.id)) or 0
    )
    return CourseRead.model_validate(
        {
            **course.__dict__,
            "document_count": document_count,
            "node_count": node_count,
            "edge_count": edge_count,
        }
    )


@router.post("", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(payload: CourseCreate, db: Session = Depends(get_db)) -> CourseRead:
    course = Course(name=payload.name, code=payload.code.upper(), description=payload.description)
    db.add(course)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="A course with this code already exists"
        ) from exc
    db.refresh(course)
    return course_read(db, course)


@router.get("", response_model=list[CourseRead])
def list_courses(db: Session = Depends(get_db)) -> list[CourseRead]:
    courses = db.scalars(select(Course).order_by(Course.updated_at.desc())).all()
    return [course_read(db, course) for course in courses]


@router.get("/{course_id}", response_model=CourseRead)
def get_course(course_id: str, db: Session = Depends(get_db)) -> CourseRead:
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course_read(db, course)
