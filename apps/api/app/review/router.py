from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.documents.router import get_storage_provider
from app.documents.service import (
    CourseNotFoundError,
    DocumentNotFoundError,
    DocumentService,
)
from app.graph.service import (
    DuplicateGraphRecord,
    GraphRecordNotFound,
    InvalidGraphReference,
    InvalidReviewTransition,
    SqlCourseGraph,
)
from app.review.service import GraphReviewService
from app.schemas import (
    BulkApproveRequest,
    BulkApproveResult,
    CandidateMerge,
    CandidateMergeResult,
    CandidateNodeDetailRead,
    CandidateNodeEdit,
    CandidateNodeRead,
    CandidateQueueRead,
    CandidateRelationshipDetailRead,
    CandidateRelationshipEdit,
    CandidateRelationshipRead,
    ReviewDecision,
)
from app.storage.base import StorageProvider

router = APIRouter(prefix="/courses/{course_id}/graph/review", tags=["graph-review"])


def get_review_service(
    db: Session = Depends(get_db),
    storage: StorageProvider = Depends(get_storage_provider),
) -> GraphReviewService:
    return GraphReviewService(SqlCourseGraph(db), DocumentService(db, storage))


def review_call[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (CourseNotFoundError, DocumentNotFoundError, GraphRecordNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidReviewTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DuplicateGraphRecord as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidGraphReference as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/candidates", response_model=CandidateQueueRead)
def list_candidates(
    course_id: str,
    document_id: str | None = Query(default=None, alias="documentId"),
    review: GraphReviewService = Depends(get_review_service),
) -> Any:
    return review_call(lambda: review.queue(course_id, document_id=document_id))


@router.get("/candidates/nodes/{node_id}", response_model=CandidateNodeDetailRead)
def get_node_candidate(
    course_id: str, node_id: str, review: GraphReviewService = Depends(get_review_service)
) -> Any:
    return review_call(lambda: review.node_detail(course_id, node_id))


@router.get(
    "/candidates/relationships/{relationship_id}",
    response_model=CandidateRelationshipDetailRead,
)
def get_relationship_candidate(
    course_id: str,
    relationship_id: str,
    review: GraphReviewService = Depends(get_review_service),
) -> Any:
    return review_call(lambda: review.relationship_detail(course_id, relationship_id))


@router.post("/candidates/nodes/{node_id}/approve", response_model=CandidateNodeRead)
def approve_node_candidate(
    course_id: str,
    node_id: str,
    db: Session = Depends(get_db),
    review: GraphReviewService = Depends(get_review_service),
) -> Any:
    result = review_call(lambda: review.approve_node(course_id, node_id))
    db.commit()
    return result


@router.post("/candidates/nodes/{node_id}/reject", response_model=CandidateNodeRead)
def reject_node_candidate(
    course_id: str,
    node_id: str,
    payload: ReviewDecision | None = None,
    db: Session = Depends(get_db),
    review: GraphReviewService = Depends(get_review_service),
) -> Any:
    note = payload.note if payload else None
    result = review_call(lambda: review.reject_node(course_id, node_id, note))
    db.commit()
    return result


@router.patch("/candidates/nodes/{node_id}", response_model=CandidateNodeRead)
def edit_node_candidate(
    course_id: str,
    node_id: str,
    payload: CandidateNodeEdit,
    db: Session = Depends(get_db),
    review: GraphReviewService = Depends(get_review_service),
) -> Any:
    values = payload.model_dump(exclude_unset=True)
    result = review_call(lambda: review.edit_node(course_id, node_id, values))
    db.commit()
    return result


@router.post("/candidates/nodes/{node_id}/merge", response_model=CandidateMergeResult)
def merge_node_candidate(
    course_id: str,
    node_id: str,
    payload: CandidateMerge,
    db: Session = Depends(get_db),
    review: GraphReviewService = Depends(get_review_service),
) -> Any:
    result = review_call(lambda: review.merge_node(course_id, node_id, payload.target_id))
    db.commit()
    return result


@router.post(
    "/candidates/relationships/{relationship_id}/approve",
    response_model=CandidateRelationshipRead,
)
def approve_relationship_candidate(
    course_id: str,
    relationship_id: str,
    db: Session = Depends(get_db),
    review: GraphReviewService = Depends(get_review_service),
) -> Any:
    result = review_call(lambda: review.approve_relationship(course_id, relationship_id))
    db.commit()
    return result


@router.post(
    "/candidates/relationships/{relationship_id}/reject",
    response_model=CandidateRelationshipRead,
)
def reject_relationship_candidate(
    course_id: str,
    relationship_id: str,
    payload: ReviewDecision | None = None,
    db: Session = Depends(get_db),
    review: GraphReviewService = Depends(get_review_service),
) -> Any:
    note = payload.note if payload else None
    result = review_call(lambda: review.reject_relationship(course_id, relationship_id, note))
    db.commit()
    return result


@router.patch(
    "/candidates/relationships/{relationship_id}", response_model=CandidateRelationshipRead
)
def edit_relationship_candidate(
    course_id: str,
    relationship_id: str,
    payload: CandidateRelationshipEdit,
    db: Session = Depends(get_db),
    review: GraphReviewService = Depends(get_review_service),
) -> Any:
    values = payload.model_dump(exclude_unset=True)
    result = review_call(lambda: review.edit_relationship(course_id, relationship_id, values))
    db.commit()
    return result


@router.post(
    "/candidates/relationships/{relationship_id}/merge", response_model=CandidateMergeResult
)
def merge_relationship_candidate(
    course_id: str,
    relationship_id: str,
    payload: CandidateMerge,
    db: Session = Depends(get_db),
    review: GraphReviewService = Depends(get_review_service),
) -> Any:
    result = review_call(
        lambda: review.merge_relationship(course_id, relationship_id, payload.target_id)
    )
    db.commit()
    return result


@router.post("/candidates/approve", response_model=BulkApproveResult)
def approve_candidates(
    course_id: str,
    payload: BulkApproveRequest,
    db: Session = Depends(get_db),
    review: GraphReviewService = Depends(get_review_service),
) -> Any:
    result = review_call(
        lambda: review.approve_many(course_id, payload.node_ids, payload.relationship_ids)
    )
    db.commit()
    return result
