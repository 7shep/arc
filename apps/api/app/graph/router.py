from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.graph.service import (
    DuplicateGraphRecord,
    GraphRecordNotFound,
    InvalidGraphReference,
    SqlCourseGraph,
)
from app.schemas import (
    GraphEdgeRead,
    GraphNeighborhoodRead,
    GraphNodeCreate,
    GraphNodeRead,
    GraphNodeUpdate,
    GraphRead,
    GraphRelationshipCreate,
    GraphRelationshipUpdate,
)

router = APIRouter(prefix="/courses/{course_id}/graph", tags=["graph"])


def graph_call[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except GraphRecordNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidGraphReference as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DuplicateGraphRecord as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=GraphRead)
def get_graph(course_id: str, db: Session = Depends(get_db)) -> GraphRead:
    graph = SqlCourseGraph(db)
    nodes, relationships = graph_call(lambda: graph.get_visualization(course_id))
    return GraphRead.model_validate({"nodes": nodes, "edges": relationships})


@router.post("/nodes", response_model=GraphNodeRead, status_code=status.HTTP_201_CREATED)
def create_node(
    course_id: str, payload: GraphNodeCreate, db: Session = Depends(get_db)
) -> Any:
    graph = SqlCourseGraph(db)
    node = graph_call(
        lambda: graph.create_node(
            course_id,
            payload.type,
            payload.label,
            description=payload.description,
            source_document_id=payload.source_document_id,
            source_location=payload.source_location,
            node_metadata=payload.metadata,
        )
    )
    db.commit()
    db.refresh(node)
    return node


@router.get("/nodes/search", response_model=list[GraphNodeRead])
def search_nodes(
    course_id: str,
    q: str = Query(min_length=1, max_length=255),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[Any]:
    if not q.strip():
        raise HTTPException(status_code=422, detail="Search query must not be blank")
    graph = SqlCourseGraph(db)
    return graph_call(lambda: graph.search_nodes(course_id, q, limit))


@router.get("/nodes/{node_id}", response_model=GraphNodeRead)
def get_node(course_id: str, node_id: str, db: Session = Depends(get_db)) -> Any:
    graph = SqlCourseGraph(db)
    return graph_call(lambda: graph.get_node(course_id, node_id))


@router.patch("/nodes/{node_id}", response_model=GraphNodeRead)
def update_node(
    course_id: str,
    node_id: str,
    payload: GraphNodeUpdate,
    db: Session = Depends(get_db),
) -> Any:
    graph = SqlCourseGraph(db)
    values = payload.model_dump(exclude_unset=True)
    node = graph_call(lambda: graph.update_node(course_id, node_id, values))
    db.commit()
    db.refresh(node)
    return node


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_node(course_id: str, node_id: str, db: Session = Depends(get_db)) -> Response:
    graph = SqlCourseGraph(db)
    graph_call(lambda: graph.archive_node(course_id, node_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/nodes/{node_id}/neighbors", response_model=GraphNeighborhoodRead)
def get_neighbors(
    course_id: str, node_id: str, db: Session = Depends(get_db)
) -> GraphNeighborhoodRead:
    graph = SqlCourseGraph(db)
    nodes, relationships = graph_call(lambda: graph.get_neighbors(course_id, node_id))
    return GraphNeighborhoodRead.model_validate(
        {"center_node_id": node_id, "nodes": nodes, "edges": relationships}
    )


@router.post(
    "/relationships", response_model=GraphEdgeRead, status_code=status.HTTP_201_CREATED
)
def create_relationship(
    course_id: str, payload: GraphRelationshipCreate, db: Session = Depends(get_db)
) -> Any:
    graph = SqlCourseGraph(db)
    relationship = graph_call(
        lambda: graph.create_relationship(
            course_id,
            payload.source_node_id,
            payload.target_node_id,
            payload.type,
            confidence=payload.confidence,
            source_document_id=payload.source_document_id,
            source_location=payload.source_location,
            edge_metadata=payload.metadata,
        )
    )
    db.commit()
    db.refresh(relationship)
    return relationship


@router.get("/relationships/{relationship_id}", response_model=GraphEdgeRead)
def get_relationship(
    course_id: str, relationship_id: str, db: Session = Depends(get_db)
) -> Any:
    graph = SqlCourseGraph(db)
    return graph_call(lambda: graph.get_relationship(course_id, relationship_id))


@router.patch("/relationships/{relationship_id}", response_model=GraphEdgeRead)
def update_relationship(
    course_id: str,
    relationship_id: str,
    payload: GraphRelationshipUpdate,
    db: Session = Depends(get_db),
) -> Any:
    graph = SqlCourseGraph(db)
    values = payload.model_dump(exclude_unset=True)
    relationship = graph_call(
        lambda: graph.update_relationship(course_id, relationship_id, values)
    )
    db.commit()
    db.refresh(relationship)
    return relationship


@router.delete(
    "/relationships/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT
)
def archive_relationship(
    course_id: str, relationship_id: str, db: Session = Depends(get_db)
) -> Response:
    graph = SqlCourseGraph(db)
    graph_call(lambda: graph.archive_relationship(course_id, relationship_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
