from typing import Any

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.graph.service import SqlCourseGraph
from app.models import (
    GraphEdge,
    GraphEdgeType,
    GraphEvidence,
    GraphNode,
    GraphNodeType,
    ReviewStatus,
)


def create_course(client: TestClient, code: str) -> dict[str, Any]:
    response = client.post("/courses", json={"name": f"Course {code}", "code": code})
    assert response.status_code == 201
    return response.json()


def upload_document(
    client: TestClient, course_id: str, name: str = "lecture.txt"
) -> dict[str, Any]:
    response = client.post(
        f"/courses/{course_id}/documents",
        data={"document_type": "LECTURE"},
        files={"file": (name, b"Trees require graphs.\nA tree is acyclic.", "text/plain")},
    )
    assert response.status_code == 201
    return response.json()


def add_candidate_node(
    course_id: str,
    document_id: str,
    label: str,
    *,
    confidence: float = 0.8,
    description: str | None = None,
    excerpt: str = "A tree is an acyclic connected graph.",
) -> str:
    with SessionLocal() as db:
        graph = SqlCourseGraph(db)
        node = graph.create_node(
            course_id,
            GraphNodeType.CONCEPT,
            label,
            description=description,
            confidence=confidence,
            review_status=ReviewStatus.PENDING,
            node_metadata={"extractor": "mcp", "model": "test"},
        )
        graph.attach_evidence(
            course_id,
            "node",
            node.id,
            document_id,
            {"page": 2, "section": "Definitions"},
            excerpt,
            confidence,
        )
        db.commit()
        return node.id


def add_candidate_relationship(
    course_id: str,
    document_id: str,
    source_node_id: str,
    target_node_id: str,
    *,
    confidence: float = 0.7,
    edge_type: GraphEdgeType = GraphEdgeType.REQUIRES,
) -> str:
    with SessionLocal() as db:
        graph = SqlCourseGraph(db)
        edge = graph.create_relationship(
            course_id,
            source_node_id,
            target_node_id,
            edge_type,
            confidence=confidence,
            review_status=ReviewStatus.PENDING,
        )
        graph.attach_evidence(
            course_id,
            "relationship",
            edge.id,
            document_id,
            {"page": 3},
            "Trees require graphs.",
            confidence,
        )
        db.commit()
        return edge.id


def add_approved_node(course_id: str, label: str, *, description: str | None = None) -> str:
    with SessionLocal() as db:
        node = SqlCourseGraph(db).create_node(
            course_id, GraphNodeType.CONCEPT, label, description=description
        )
        db.commit()
        return node.id


def review_url(course_id: str) -> str:
    return f"/courses/{course_id}/graph/review/candidates"


def test_pending_queue_and_candidate_detail_expose_source_evidence(client: TestClient) -> None:
    course = create_course(client, "RV100")
    document = upload_document(client, course["id"])
    add_approved_node(course["id"], "Graph theory")
    node_id = add_candidate_node(course["id"], document["id"], "Graph")
    relationship_source = add_candidate_node(course["id"], document["id"], "Tree")
    relationship_id = add_candidate_relationship(
        course["id"], document["id"], relationship_source, node_id
    )

    queue = client.get(review_url(course["id"]))
    assert queue.status_code == 200
    body = queue.json()
    assert body["pendingCount"] == 3
    assert {item["label"] for item in body["nodes"]} == {"Graph", "Tree"}
    assert body["nodes"][0]["reviewStatus"] == "PENDING"
    assert body["nodes"][0]["metadata"]["extractor"] == "mcp"
    assert body["relationships"][0]["id"] == relationship_id

    detail = client.get(f"{review_url(course['id'])}/nodes/{node_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["candidate"]["confidence"] == 0.8
    assert detail_body["candidate"]["sourceDocumentName"] == "lecture.txt"
    evidence = detail_body["evidence"][0]
    assert evidence["excerpt"] == "A tree is an acyclic connected graph."
    assert evidence["page"] == 2
    assert evidence["section"] == "Definitions"
    assert evidence["documentName"] == "lecture.txt"
    assert [node["label"] for node in detail_body["relatedNodes"]] == ["Graph theory"]

    relationship_detail = client.get(
        f"{review_url(course['id'])}/relationships/{relationship_id}"
    )
    assert relationship_detail.status_code == 200
    relationship_body = relationship_detail.json()
    assert relationship_body["candidate"]["sourceNodeLabel"] == "Tree"
    assert relationship_body["evidence"][0]["excerpt"] == "Trees require graphs."
    assert len(relationship_body["relatedNodes"]) == 2


def test_candidates_are_hidden_from_the_approved_graph_until_approved(
    client: TestClient,
) -> None:
    course = create_course(client, "RV101")
    document = upload_document(client, course["id"])
    node_id = add_candidate_node(course["id"], document["id"], "Graph")

    graph = client.get(f"/courses/{course['id']}/graph").json()
    assert graph["nodes"] == []
    assert client.get(f"/courses/{course['id']}").json()["nodeCount"] == 0

    approved = client.post(f"{review_url(course['id'])}/nodes/{node_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["reviewStatus"] == "APPROVED"
    assert approved.json()["reviewedAt"]

    graph = client.get(f"/courses/{course['id']}/graph").json()
    assert [node["label"] for node in graph["nodes"]] == ["Graph"]
    assert client.get(f"/courses/{course['id']}").json()["nodeCount"] == 1
    assert client.get(review_url(course["id"])).json()["pendingCount"] == 0


def test_relationship_approval_requires_approved_endpoints(client: TestClient) -> None:
    course = create_course(client, "RV102")
    document = upload_document(client, course["id"])
    source_id = add_candidate_node(course["id"], document["id"], "Tree")
    target_id = add_candidate_node(course["id"], document["id"], "Graph")
    relationship_id = add_candidate_relationship(
        course["id"], document["id"], source_id, target_id
    )

    blocked = client.post(f"{review_url(course['id'])}/relationships/{relationship_id}/approve")
    assert blocked.status_code == 422
    assert "connected nodes" in blocked.json()["detail"]

    for node_id in (source_id, target_id):
        assert client.post(f"{review_url(course['id'])}/nodes/{node_id}/approve").status_code == 200
    approved = client.post(f"{review_url(course['id'])}/relationships/{relationship_id}/approve")
    assert approved.status_code == 200
    graph = client.get(f"/courses/{course['id']}/graph").json()
    assert len(graph["edges"]) == 1


def test_duplicate_approval_is_rejected_and_leaves_the_graph_untouched(
    client: TestClient,
) -> None:
    course = create_course(client, "RV103")
    document = upload_document(client, course["id"])
    node_id = add_candidate_node(course["id"], document["id"], "Graph")

    assert client.post(f"{review_url(course['id'])}/nodes/{node_id}/approve").status_code == 200
    repeat = client.post(f"{review_url(course['id'])}/nodes/{node_id}/approve")
    assert repeat.status_code == 409
    assert "already approved" in repeat.json()["detail"]
    graph = client.get(f"/courses/{course['id']}/graph").json()
    assert len(graph["nodes"]) == 1


def test_approving_a_duplicate_label_fails_and_the_candidate_stays_reviewable(
    client: TestClient,
) -> None:
    course = create_course(client, "RV104")
    document = upload_document(client, course["id"])
    add_approved_node(course["id"], "Graph")
    node_id = add_candidate_node(course["id"], document["id"], "Graph")

    conflict = client.post(f"{review_url(course['id'])}/nodes/{node_id}/approve")
    assert conflict.status_code == 409

    graph = client.get(f"/courses/{course['id']}/graph").json()
    assert len(graph["nodes"]) == 1
    queue = client.get(review_url(course["id"])).json()
    assert queue["pendingCount"] == 1
    assert queue["nodes"][0]["reviewStatus"] == "PENDING"
    with SessionLocal() as db:
        assert db.query(GraphEvidence).count() == 1


def test_rejection_removes_the_candidate_without_changing_approved_data(
    client: TestClient,
) -> None:
    course = create_course(client, "RV105")
    document = upload_document(client, course["id"])
    approved_id = add_approved_node(course["id"], "Graph theory")
    node_id = add_candidate_node(course["id"], document["id"], "Grahp")
    relationship_id = add_candidate_relationship(
        course["id"], document["id"], node_id, approved_id
    )

    rejected = client.post(
        f"{review_url(course['id'])}/nodes/{node_id}/reject",
        json={"note": "Typo extracted from the slide title"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["reviewStatus"] == "REJECTED"
    assert rejected.json()["reviewNote"] == "Typo extracted from the slide title"

    graph = client.get(f"/courses/{course['id']}/graph").json()
    assert [node["id"] for node in graph["nodes"]] == [approved_id]
    assert graph["edges"] == []
    assert client.get(review_url(course["id"])).json()["pendingCount"] == 0
    with SessionLocal() as db:
        assert db.get(GraphEdge, relationship_id).review_status is ReviewStatus.REJECTED
        assert db.get(GraphNode, approved_id).review_status is ReviewStatus.APPROVED
        assert db.query(GraphEvidence).count() == 2

    repeat = client.post(f"{review_url(course['id'])}/nodes/{node_id}/reject")
    assert repeat.status_code == 409


def test_editing_a_candidate_keeps_it_in_review_until_approved(client: TestClient) -> None:
    course = create_course(client, "RV106")
    document = upload_document(client, course["id"])
    node_id = add_candidate_node(course["id"], document["id"], "grahp")

    edited = client.patch(
        f"{review_url(course['id'])}/nodes/{node_id}",
        json={"label": "Graph", "description": "A set of vertices and edges", "type": "CONCEPT"},
    )
    assert edited.status_code == 200
    assert edited.json()["reviewStatus"] == "EDITED"
    assert edited.json()["label"] == "Graph"
    assert client.get(f"/courses/{course['id']}/graph").json()["nodes"] == []
    assert client.get(review_url(course["id"])).json()["pendingCount"] == 1

    approved = client.post(f"{review_url(course['id'])}/nodes/{node_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["metadata"]["review"]["edited"] is True
    graph = client.get(f"/courses/{course['id']}/graph").json()
    assert [node["label"] for node in graph["nodes"]] == ["Graph"]

    assert (
        client.patch(f"{review_url(course['id'])}/nodes/{node_id}", json={"label": "X"}).status_code
        == 409
    )


def test_editing_validates_confidence_and_empty_payloads(client: TestClient) -> None:
    course = create_course(client, "RV107")
    document = upload_document(client, course["id"])
    node_id = add_candidate_node(course["id"], document["id"], "Graph")

    assert (
        client.patch(
            f"{review_url(course['id'])}/nodes/{node_id}", json={"confidence": 1.4}
        ).status_code
        == 422
    )
    assert client.patch(f"{review_url(course['id'])}/nodes/{node_id}", json={}).status_code == 422
    queue = client.get(review_url(course["id"])).json()
    assert queue["nodes"][0]["confidence"] == 0.8


def test_merging_a_candidate_node_preserves_provenance_without_duplicates(
    client: TestClient,
) -> None:
    course = create_course(client, "RV108")
    document = upload_document(client, course["id"])
    target_id = add_approved_node(course["id"], "Graph")
    other_id = add_approved_node(course["id"], "Tree")
    with SessionLocal() as db:
        SqlCourseGraph(db).create_relationship(
            course["id"], other_id, target_id, GraphEdgeType.REQUIRES
        )
        db.commit()

    candidate_id = add_candidate_node(
        course["id"], document["id"], "Graphs", description="A set of vertices and edges"
    )
    duplicate_edge_id = add_candidate_relationship(
        course["id"], document["id"], other_id, candidate_id
    )
    new_edge_id = add_candidate_relationship(
        course["id"],
        document["id"],
        candidate_id,
        other_id,
        edge_type=GraphEdgeType.RELATED_TO,
    )

    merged = client.post(
        f"{review_url(course['id'])}/nodes/{candidate_id}/merge",
        json={"targetId": target_id},
    )
    assert merged.status_code == 200
    body = merged.json()
    assert body["candidateId"] == candidate_id
    assert body["targetNode"]["id"] == target_id
    assert body["targetNode"]["description"] == "A set of vertices and edges"
    provenance = body["targetNode"]["metadata"]["provenance"]["mergedCandidates"]
    assert provenance[0]["candidateId"] == candidate_id
    assert provenance[0]["label"] == "Graphs"
    assert provenance[0]["metadata"]["extractor"] == "mcp"

    graph = client.get(f"/courses/{course['id']}/graph").json()
    assert sorted(node["label"] for node in graph["nodes"]) == ["Graph", "Tree"]

    with SessionLocal() as db:
        candidate = db.get(GraphNode, candidate_id)
        assert candidate.review_status is ReviewStatus.MERGED
        assert candidate.merged_into_node_id == target_id
        assert candidate.archived_at is not None
        assert db.query(GraphEvidence).filter_by(graph_node_id=target_id).count() == 1
        assert db.query(GraphEvidence).filter_by(graph_node_id=candidate_id).count() == 0
        duplicate_edge = db.get(GraphEdge, duplicate_edge_id)
        assert duplicate_edge.review_status is ReviewStatus.MERGED
        assert duplicate_edge.merged_into_edge_id is not None
        moved_edge = db.get(GraphEdge, new_edge_id)
        assert moved_edge.source_node_id == target_id
        assert moved_edge.review_status is ReviewStatus.PENDING
        assert db.query(GraphEvidence).count() == 3

    assert (
        client.post(
            f"{review_url(course['id'])}/nodes/{candidate_id}/merge",
            json={"targetId": target_id},
        ).status_code
        == 409
    )


def test_merging_a_candidate_relationship_moves_evidence_to_the_approved_edge(
    client: TestClient,
) -> None:
    course = create_course(client, "RV109")
    document = upload_document(client, course["id"])
    source_id = add_approved_node(course["id"], "Tree")
    target_id = add_approved_node(course["id"], "Graph")
    with SessionLocal() as db:
        approved_edge = SqlCourseGraph(db).create_relationship(
            course["id"], source_id, target_id, GraphEdgeType.REQUIRES
        )
        db.commit()
        approved_edge_id = approved_edge.id

    candidate_edge_id = add_candidate_relationship(
        course["id"], document["id"], source_id, target_id, edge_type=GraphEdgeType.RELATED_TO
    )
    merged = client.post(
        f"{review_url(course['id'])}/relationships/{candidate_edge_id}/merge",
        json={"targetId": approved_edge_id},
    )
    assert merged.status_code == 200
    assert merged.json()["targetRelationship"]["confidence"] == 0.7

    graph = client.get(f"/courses/{course['id']}/graph").json()
    assert [edge["id"] for edge in graph["edges"]] == [approved_edge_id]
    with SessionLocal() as db:
        assert db.query(GraphEvidence).filter_by(graph_edge_id=approved_edge_id).count() == 1
        candidate = db.get(GraphEdge, candidate_edge_id)
        assert candidate.review_status is ReviewStatus.MERGED
        assert candidate.merged_into_edge_id == approved_edge_id


def test_merge_rejects_unknown_and_unapproved_targets(client: TestClient) -> None:
    course = create_course(client, "RV110")
    document = upload_document(client, course["id"])
    candidate_id = add_candidate_node(course["id"], document["id"], "Graphs")
    other_candidate_id = add_candidate_node(course["id"], document["id"], "Trees")

    missing = client.post(
        f"{review_url(course['id'])}/nodes/{candidate_id}/merge",
        json={"targetId": "00000000-0000-0000-0000-000000000000"},
    )
    assert missing.status_code == 422
    unapproved = client.post(
        f"{review_url(course['id'])}/nodes/{candidate_id}/merge",
        json={"targetId": other_candidate_id},
    )
    assert unapproved.status_code == 422
    itself = client.post(
        f"{review_url(course['id'])}/nodes/{candidate_id}/merge",
        json={"targetId": candidate_id},
    )
    assert itself.status_code == 422
    assert client.get(review_url(course["id"])).json()["pendingCount"] == 2


def test_bulk_approval_applies_valid_candidates_and_reports_failures(
    client: TestClient,
) -> None:
    course = create_course(client, "RV111")
    document = upload_document(client, course["id"])
    add_approved_node(course["id"], "Graph")
    first = add_candidate_node(course["id"], document["id"], "Tree")
    second = add_candidate_node(course["id"], document["id"], "Forest")
    conflicting = add_candidate_node(course["id"], document["id"], "Graph")
    relationship_id = add_candidate_relationship(course["id"], document["id"], first, second)

    result = client.post(
        f"{review_url(course['id'])}/approve",
        json={
            "nodeIds": [first, second, conflicting, "missing-id"],
            "relationshipIds": [relationship_id],
        },
    )
    assert result.status_code == 200
    body = result.json()
    assert body["approvedNodeIds"] == [first, second]
    assert body["approvedRelationshipIds"] == [relationship_id]
    assert {failure["id"] for failure in body["failures"]} == {conflicting, "missing-id"}

    graph = client.get(f"/courses/{course['id']}/graph").json()
    assert sorted(node["label"] for node in graph["nodes"]) == ["Forest", "Graph", "Tree"]
    assert len(graph["edges"]) == 1
    queue = client.get(review_url(course["id"])).json()
    assert queue["pendingCount"] == 1
    assert queue["nodes"][0]["id"] == conflicting

    assert (
        client.post(f"{review_url(course['id'])}/approve", json={"nodeIds": []}).status_code == 422
    )


def test_review_rejects_unknown_records_and_cross_course_access(client: TestClient) -> None:
    first = create_course(client, "RV112")
    second = create_course(client, "RV113")
    document = upload_document(client, first["id"])
    node_id = add_candidate_node(first["id"], document["id"], "Graph")

    assert client.get(review_url("missing-course")).status_code == 404
    assert (
        client.get(
            f"{review_url(first['id'])}/nodes/00000000-0000-0000-0000-000000000000"
        ).status_code
        == 404
    )
    assert client.get(f"{review_url(second['id'])}/nodes/{node_id}").status_code == 404
    assert (
        client.post(f"{review_url(second['id'])}/nodes/{node_id}/approve").status_code == 404
    )
    assert (
        client.post(f"{review_url(second['id'])}/nodes/{node_id}/reject").status_code == 404
    )
    assert client.get(f"{review_url(first['id'])}?documentId=missing").status_code == 404
    assert client.get(review_url(first["id"])).json()["pendingCount"] == 1


def test_queue_can_be_filtered_by_source_document(client: TestClient) -> None:
    course = create_course(client, "RV114")
    first_document = upload_document(client, course["id"], "first.txt")
    second_document = upload_document(client, course["id"], "second.txt")
    first_node = add_candidate_node(course["id"], first_document["id"], "Graph")
    add_candidate_node(course["id"], second_document["id"], "Tree")

    filtered = client.get(f"{review_url(course['id'])}?documentId={first_document['id']}").json()
    assert [node["id"] for node in filtered["nodes"]] == [first_node]
    assert filtered["pendingCount"] == 1
