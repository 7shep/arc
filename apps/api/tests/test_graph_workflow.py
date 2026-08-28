"""End-to-end course graph workflow.

Upload a lecture, process it into source-aware chunks, read those chunks over MCP, create
candidate records from them, review and approve the candidates, and confirm the approved graph
and its provenance are what the workspace renders.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from app.config import get_settings
from app.database import SessionLocal
from app.mcp.server import create_mcp_server
from app.models import GraphEvidence
from app.storage.local import LocalStorageProvider

LECTURE = b"""# Lecture 07: Green's theorem

Green's theorem relates a line integral around a simple closed curve to a double integral.

## Prerequisites

Line integrals are required before Green's theorem.
"""


@pytest.fixture
def mcp_server():
    return create_mcp_server(
        SessionLocal, lambda: LocalStorageProvider(get_settings().upload_dir)
    )


def create_course(client: TestClient, code: str = "MATH221") -> dict[str, Any]:
    response = client.post("/courses", json={"name": "Vector Calculus", "code": code})
    assert response.status_code == 201
    return response.json()


def upload_lecture(
    client: TestClient, course_id: str, name: str = "lecture-07.md", body: bytes = LECTURE
) -> dict[str, Any]:
    response = client.post(
        f"/courses/{course_id}/documents",
        data={"document_type": "LECTURE"},
        files={"file": (name, body, "text/markdown")},
    )
    assert response.status_code == 201
    return response.json()


def evidence_input(document_id: str) -> dict[str, Any]:
    return {
        "document_id": document_id,
        "source_location": {"page": 1, "section": "Lecture 07: Green's theorem"},
        "excerpt": "Green's theorem relates a line integral around a simple closed curve.",
        "confidence": 0.86,
    }


@pytest.mark.anyio
async def test_document_to_reviewed_graph_workflow(client: TestClient, mcp_server) -> None:
    course = create_course(client)
    document = upload_lecture(client, course["id"])
    assert document["processingStatus"] == "UPLOADED"

    unprocessed = client.get(f"/courses/{course['id']}/documents").json()
    assert [item["processingStatus"] for item in unprocessed] == ["UPLOADED"]
    assert unprocessed[0]["chunkCount"] == 0

    processed = client.post(
        f"/courses/{course['id']}/documents/{document['id']}/process"
    )
    assert processed.status_code == 200
    assert processed.json()["processingStatus"] == "READY"
    assert processed.json()["processingError"] is None
    chunk_count = processed.json()["chunkCount"]
    assert chunk_count > 0

    async with Client(mcp_server) as mcp_client:
        chunks = await mcp_client.call_tool(
            "get_document_chunks",
            {"course_id": course["id"], "document_id": document["id"]},
        )
        assert len(chunks.structured_content["chunks"]) == chunk_count
        assert "Green's theorem" in chunks.structured_content["chunks"][0]["content"]

        theorem = await mcp_client.call_tool(
            "create_candidate_node",
            {
                "course_id": course["id"],
                "node_type": "CONCEPT",
                "label": "Green's theorem",
                "description": "Relates a line integral to a double integral.",
                **evidence_input(document["id"]),
            },
        )
        integrals = await mcp_client.call_tool(
            "create_candidate_node",
            {
                "course_id": course["id"],
                "node_type": "CONCEPT",
                "label": "Line integrals",
                **evidence_input(document["id"]),
            },
        )
        relationship = await mcp_client.call_tool(
            "create_candidate_relationship",
            {
                "course_id": course["id"],
                "source_node_id": theorem.structured_content["id"],
                "target_node_id": integrals.structured_content["id"],
                "relationship_type": "REQUIRES",
                **evidence_input(document["id"]),
            },
        )
        await mcp_client.call_tool(
            "mark_document_processed",
            {"course_id": course["id"], "document_id": document["id"]},
        )

    theorem_id = theorem.structured_content["id"]
    integrals_id = integrals.structured_content["id"]
    relationship_id = relationship.structured_content["id"]

    review_url = f"/courses/{course['id']}/graph/review/candidates"
    queue = client.get(review_url).json()
    assert queue["pendingCount"] == 3
    assert client.get(f"/courses/{course['id']}/graph").json() == {"nodes": [], "edges": []}

    document_graph = client.get(
        f"/courses/{course['id']}/documents/{document['id']}/graph"
    ).json()
    assert document_graph["pendingCandidateCount"] == 3
    assert document_graph["nodes"] == []
    assert document_graph["chunkCount"] == chunk_count

    detail = client.get(f"{review_url}/nodes/{theorem_id}").json()
    assert detail["evidence"][0]["documentName"] == "lecture-07.md"
    assert detail["evidence"][0]["section"] == "Lecture 07: Green's theorem"

    approved = client.post(
        f"{review_url}/approve",
        json={"nodeIds": [theorem_id, integrals_id], "relationshipIds": [relationship_id]},
    ).json()
    assert approved["approvedNodeIds"] == [theorem_id, integrals_id]
    assert approved["approvedRelationshipIds"] == [relationship_id]
    assert approved["failures"] == []

    graph = client.get(f"/courses/{course['id']}/graph").json()
    assert sorted(node["label"] for node in graph["nodes"]) == [
        "Green's theorem",
        "Line integrals",
    ]
    assert [edge["id"] for edge in graph["edges"]] == [relationship_id]
    assert client.get(f"/courses/{course['id']}").json()["nodeCount"] == 2
    assert client.get(review_url).json()["pendingCount"] == 0

    document_graph = client.get(
        f"/courses/{course['id']}/documents/{document['id']}/graph"
    ).json()
    assert sorted(node["id"] for node in document_graph["nodes"]) == sorted(
        [theorem_id, integrals_id]
    )
    assert [edge["id"] for edge in document_graph["edges"]] == [relationship_id]
    assert document_graph["pendingCandidateCount"] == 0

    with SessionLocal() as db:
        evidence = db.query(GraphEvidence).all()
        assert len(evidence) == 3
        assert {item.document_id for item in evidence} == {document["id"]}
        assert all(item.excerpt.startswith("Green's theorem relates") for item in evidence)


@pytest.mark.anyio
async def test_reprocessing_and_repeated_approval_create_no_duplicates(
    client: TestClient, mcp_server
) -> None:
    course = create_course(client, "MATH222")
    document = upload_lecture(client, course["id"])
    first = client.post(f"/courses/{course['id']}/documents/{document['id']}/process").json()
    second = client.post(f"/courses/{course['id']}/documents/{document['id']}/process").json()
    assert first["chunkCount"] == second["chunkCount"]

    chunks = client.get(f"/courses/{course['id']}/documents/{document['id']}/chunks").json()
    assert len(chunks) == second["chunkCount"]
    assert [chunk["sequence"] for chunk in chunks] == list(range(len(chunks)))

    async with Client(mcp_server) as mcp_client:
        node = await mcp_client.call_tool(
            "create_candidate_node",
            {
                "course_id": course["id"],
                "node_type": "CONCEPT",
                "label": "Green's theorem",
                **evidence_input(document["id"]),
            },
        )
        repeated = await mcp_client.call_tool(
            "create_candidate_node",
            {
                "course_id": course["id"],
                "node_type": "CONCEPT",
                "label": "Green's theorem",
                **evidence_input(document["id"]),
            },
        )

    node_id = node.structured_content["id"]
    repeated_id = repeated.structured_content["id"]
    review_url = f"/courses/{course['id']}/graph/review/candidates"
    assert client.get(review_url).json()["pendingCount"] == 2

    assert client.post(f"{review_url}/nodes/{node_id}/approve").status_code == 200
    assert client.post(f"{review_url}/nodes/{node_id}/approve").status_code == 409
    duplicate = client.post(f"{review_url}/nodes/{repeated_id}/approve")
    assert duplicate.status_code == 409

    graph = client.get(f"/courses/{course['id']}/graph").json()
    assert [item["label"] for item in graph["nodes"]] == ["Green's theorem"]

    merged = client.post(
        f"{review_url}/nodes/{repeated_id}/merge", json={"targetId": node_id}
    )
    assert merged.status_code == 200
    graph = client.get(f"/courses/{course['id']}/graph").json()
    assert len(graph["nodes"]) == 1
    document_graph = client.get(
        f"/courses/{course['id']}/documents/{document['id']}/graph"
    ).json()
    assert [item["id"] for item in document_graph["nodes"]] == [node_id]
    assert document_graph["pendingCandidateCount"] == 0
    with SessionLocal() as db:
        assert db.query(GraphEvidence).filter_by(graph_node_id=node_id).count() == 2


def test_processing_failure_is_reported_on_the_document(client: TestClient) -> None:
    course = create_course(client, "MATH223")
    document = upload_lecture(client, course["id"], name="empty.md", body=b"   \n")

    failed = client.post(f"/courses/{course['id']}/documents/{document['id']}/process")
    assert failed.status_code == 422
    assert "Document processing failed" in failed.json()["detail"]

    documents = client.get(f"/courses/{course['id']}/documents").json()
    assert documents[0]["processingStatus"] == "FAILED"
    assert "extractable text" in documents[0]["processingError"]
    assert documents[0]["chunkCount"] == 0

    recovered = client.post(
        f"/courses/{course['id']}/documents/{document['id']}/process",
    )
    assert recovered.status_code == 422
    assert client.get(f"/courses/{course['id']}/graph").json()["nodes"] == []
