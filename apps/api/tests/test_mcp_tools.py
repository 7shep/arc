from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from app.config import get_settings
from app.database import SessionLocal
from app.mcp.server import create_mcp_server
from app.models import GraphEvidence, GraphNode, ReviewStatus
from app.storage.local import LocalStorageProvider


def create_course(client: TestClient, code: str) -> dict[str, Any]:
    response = client.post("/courses", json={"name": f"Course {code}", "code": code})
    assert response.status_code == 201
    return response.json()


def upload_document(client: TestClient, course_id: str, name: str = "notes.txt") -> dict[str, Any]:
    response = client.post(
        f"/courses/{course_id}/documents",
        data={"document_type": "LECTURE"},
        files={"file": (name, b"Trees require graphs.\nA tree is acyclic.", "text/plain")},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def mcp_server():
    return create_mcp_server(
        SessionLocal,
        lambda: LocalStorageProvider(get_settings().upload_dir),
    )


@pytest.mark.anyio
async def test_document_discovery_metadata_and_source_aware_chunks(
    client: TestClient, mcp_server
) -> None:
    course = create_course(client, "CS201")
    document = upload_document(client, course["id"])

    async with Client(mcp_server) as mcp_client:
        tools = await mcp_client.list_tools()
        listed = await mcp_client.call_tool(
            "list_course_documents", {"course_id": course["id"]}
        )
        metadata = await mcp_client.call_tool(
            "get_document_metadata",
            {"course_id": course["id"], "document_id": document["id"]},
        )
        chunks = await mcp_client.call_tool(
            "get_document_chunks",
            {"course_id": course["id"], "document_id": document["id"]},
        )

    tools_by_name = {tool.name: tool for tool in tools.tools}
    assert set(tools_by_name) == {
        "list_course_documents",
        "get_document_metadata",
        "get_document_chunks",
        "create_candidate_node",
        "create_candidate_relationship",
        "attach_source_evidence",
        "mark_document_processed",
        "report_document_processing_failure",
    }
    confidence_schema = tools_by_name["create_candidate_node"].input_schema["properties"][
        "confidence"
    ]
    assert confidence_schema["minimum"] == 0
    assert confidence_schema["maximum"] == 1
    assert not listed.is_error
    assert not metadata.is_error
    assert not chunks.is_error, chunks.content
    assert [item["id"] for item in listed.structured_content["documents"]] == [document["id"]]
    assert listed.structured_content["documents"][0]["processing_status"] == "READY"
    assert metadata.structured_content["original_filename"] == "notes.txt"
    assert chunks.structured_content["chunks"][0]["content"].startswith("Trees require")
    # Uploads are chunked by the ingestion pipeline, which records line-level locations.
    location = chunks.structured_content["chunks"][0]["source_location"]
    assert location == {"type": "lines", "start": 1, "end": 2}


@pytest.mark.anyio
async def test_invalid_ids_and_cross_course_document_access(
    client: TestClient, mcp_server
) -> None:
    first = create_course(client, "CS202")
    second = create_course(client, "CS203")
    document = upload_document(client, first["id"])

    async with Client(mcp_server) as mcp_client:
        invalid = await mcp_client.call_tool(
            "get_document_metadata", {"course_id": "not-a-uuid", "document_id": document["id"]}
        )
        crossed = await mcp_client.call_tool(
            "get_document_metadata",
            {"course_id": second["id"], "document_id": document["id"]},
        )

    assert invalid.is_error
    assert crossed.is_error
    assert "Document not found in course" in crossed.content[0].text


@pytest.mark.anyio
async def test_candidate_node_and_relationship_preserve_provenance(
    client: TestClient, mcp_server
) -> None:
    course = create_course(client, "CS204")
    document = upload_document(client, course["id"])
    evidence_input = {
        "document_id": document["id"],
        "source_location": {"start_offset": 0, "end_offset": 20},
        "excerpt": "Trees require graphs.",
        "confidence": 0.82,
    }

    async with Client(mcp_server) as mcp_client:
        graph_node = await mcp_client.call_tool(
            "create_candidate_node",
            {
                "course_id": course["id"],
                "node_type": "CONCEPT",
                "label": "Graphs",
                **evidence_input,
            },
        )
        tree_node = await mcp_client.call_tool(
            "create_candidate_node",
            {
                "course_id": course["id"],
                "node_type": "CONCEPT",
                "label": "Trees",
                **evidence_input,
            },
        )
        relationship = await mcp_client.call_tool(
            "create_candidate_relationship",
            {
                "course_id": course["id"],
                "source_node_id": tree_node.structured_content["id"],
                "target_node_id": graph_node.structured_content["id"],
                "relationship_type": "REQUIRES",
                **evidence_input,
            },
        )
        attached = await mcp_client.call_tool(
            "attach_source_evidence",
            {
                "course_id": course["id"],
                "target_type": "relationship",
                "target_id": relationship.structured_content["id"],
                **evidence_input,
            },
        )

    assert graph_node.structured_content["review_status"] == "PENDING"
    assert relationship.structured_content["review_status"] == "PENDING"
    assert relationship.structured_content["evidence"]["document_id"] == document["id"]
    assert attached.structured_content["confidence"] == 0.82
    with SessionLocal() as db:
        node = db.get(GraphNode, graph_node.structured_content["id"])
        assert node.review_status == ReviewStatus.PENDING
        assert node.source_document_id == document["id"]
        assert db.query(GraphEvidence).count() == 4


@pytest.mark.anyio
async def test_invalid_graph_data_and_cross_course_nodes(
    client: TestClient, mcp_server
) -> None:
    first = create_course(client, "CS205")
    second = create_course(client, "CS206")
    first_document = upload_document(client, first["id"], "first.txt")
    second_document = upload_document(client, second["id"], "second.txt")
    common = {
        "source_location": {"page": 1},
        "excerpt": "Evidence",
        "confidence": 0.5,
    }
    async with Client(mcp_server) as mcp_client:
        invalid_type = await mcp_client.call_tool(
            "create_candidate_node",
            {
                "course_id": first["id"],
                "node_type": "INVALID",
                "label": "Bad",
                "document_id": first_document["id"],
                **common,
            },
        )
        invalid_location = await mcp_client.call_tool(
            "create_candidate_node",
            {
                "course_id": first["id"],
                "node_type": "CONCEPT",
                "label": "Bad location",
                "document_id": first_document["id"],
                "source_location": {"start_offset": 10, "end_offset": 2},
                "excerpt": "Evidence",
                "confidence": 0.5,
            },
        )
        invalid_confidence = await mcp_client.call_tool(
            "create_candidate_node",
            {
                "course_id": first["id"],
                "node_type": "CONCEPT",
                "label": "Bad confidence",
                "document_id": first_document["id"],
                "source_location": {"page": 1},
                "excerpt": "Evidence",
                "confidence": 1.1,
            },
        )
        first_node = await mcp_client.call_tool(
            "create_candidate_node",
            {
                "course_id": first["id"],
                "node_type": "CONCEPT",
                "label": "First node",
                "document_id": first_document["id"],
                **common,
            },
        )
        second_node = await mcp_client.call_tool(
            "create_candidate_node",
            {
                "course_id": second["id"],
                "node_type": "CONCEPT",
                "label": "Second node",
                "document_id": second_document["id"],
                **common,
            },
        )
        invalid_relationship_type = await mcp_client.call_tool(
            "create_candidate_relationship",
            {
                "course_id": first["id"],
                "source_node_id": first_node.structured_content["id"],
                "target_node_id": second_node.structured_content["id"],
                "relationship_type": "INVALID",
                "document_id": first_document["id"],
                **common,
            },
        )
        crossed = await mcp_client.call_tool(
            "create_candidate_relationship",
            {
                "course_id": first["id"],
                "source_node_id": first_node.structured_content["id"],
                "target_node_id": second_node.structured_content["id"],
                "relationship_type": "RELATED_TO",
                "document_id": first_document["id"],
                **common,
            },
        )

    assert invalid_type.is_error
    assert invalid_location.is_error
    assert invalid_confidence.is_error
    assert invalid_relationship_type.is_error
    assert crossed.is_error
    assert "must be active nodes in this course" in crossed.content[0].text


@pytest.mark.anyio
async def test_processing_success_failure_and_processed_filter(
    client: TestClient, mcp_server
) -> None:
    course = create_course(client, "CS207")
    successful = upload_document(client, course["id"], "success.txt")
    failed = upload_document(client, course["id"], "failed.txt")

    async with Client(mcp_server) as mcp_client:
        processed = await mcp_client.call_tool(
            "mark_document_processed",
            {"course_id": course["id"], "document_id": successful["id"]},
        )
        failure = await mcp_client.call_tool(
            "report_document_processing_failure",
            {
                "course_id": course["id"],
                "document_id": failed["id"],
                "reason": "Parser rejected malformed source",
            },
        )
        unprocessed = await mcp_client.call_tool(
            "list_course_documents",
            {"course_id": course["id"], "include_processed": False},
        )

    assert processed.structured_content["processing_status"] == "READY"
    assert failure.structured_content["processing_status"] == "FAILED"
    assert failure.structured_content["processing_error"] == "Parser rejected malformed source"
    assert [item["id"] for item in unprocessed.structured_content["documents"]] == [failed["id"]]
