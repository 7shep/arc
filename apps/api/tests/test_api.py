from fastapi.testclient import TestClient


def create_course(client: TestClient) -> dict:
    response = client.post(
        "/courses",
        json={"name": "Vector Calculus", "code": "math221", "description": "Test course"},
    )
    assert response.status_code == 201
    return response.json()


def create_node(client: TestClient, course_id: str, **overrides) -> dict:
    payload = {"type": "CONCEPT", "label": "Vector spaces", **overrides}
    response = client.post(f"/courses/{course_id}/graph/nodes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def upload_source(client: TestClient, course_id: str, name: str = "lecture-01.txt") -> dict:
    response = client.post(
        f"/courses/{course_id}/documents",
        data={"document_type": "LECTURE"},
        files={"file": (name, b"vectors", "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_course_lifecycle_and_duplicate_code(client: TestClient) -> None:
    course = create_course(client)
    assert course["code"] == "MATH221"
    assert course["documentCount"] == 0
    assert client.get(f"/courses/{course['id']}").status_code == 200
    assert len(client.get("/courses").json()) == 1
    duplicate = client.post("/courses", json={"name": "Other", "code": "MATH221"})
    assert duplicate.status_code == 409


def test_upload_and_list_document(client: TestClient) -> None:
    course = create_course(client)
    response = client.post(
        f"/courses/{course['id']}/documents",
        data={"document_type": "LECTURE"},
        files={"file": ("lecture-01.txt", b"vectors", "text/plain")},
    )
    assert response.status_code == 201
    document = response.json()
    assert document["originalFilename"] == "lecture-01.txt"
    assert document["processingStatus"] == "UPLOADED"
    assert len(client.get(f"/courses/{course['id']}/documents").json()) == 1


def test_rejects_unsupported_upload(client: TestClient) -> None:
    course = create_course(client)
    response = client.post(
        f"/courses/{course['id']}/documents",
        data={"document_type": "OTHER"},
        files={"file": ("archive.zip", b"bad", "application/zip")},
    )
    assert response.status_code == 415


def test_empty_graph(client: TestClient) -> None:
    course = create_course(client)
    response = client.get(f"/courses/{course['id']}/graph")
    assert response.status_code == 200
    assert response.json() == {"nodes": [], "edges": []}


def test_missing_course_routes(client: TestClient) -> None:
    assert client.get("/courses/missing").status_code == 404
    assert client.get("/courses/missing/documents").status_code == 404
    assert client.get("/courses/missing/graph").status_code == 404


def test_graph_node_lifecycle_search_and_provenance(client: TestClient) -> None:
    course = create_course(client)
    document = upload_source(client, course["id"])
    node = create_node(
        client,
        course["id"],
        description="A vector space over a field",
        sourceDocumentId=document["id"],
        sourceLocation="page 4",
        metadata={"symbol": "V"},
    )
    assert node["sourceDocumentId"] == document["id"]
    assert node["sourceLocation"] == "page 4"
    assert node["metadata"] == {"symbol": "V"}
    assert client.get(f"/courses/{course['id']}/graph/nodes/{node['id']}").json() == node

    updated = client.patch(
        f"/courses/{course['id']}/graph/nodes/{node['id']}",
        json={"label": "Finite vector spaces", "metadata": {"dimension": 3}},
    )
    assert updated.status_code == 200
    assert updated.json()["label"] == "Finite vector spaces"
    assert updated.json()["metadata"] == {"dimension": 3}
    search = client.get(
        f"/courses/{course['id']}/graph/nodes/search", params={"q": "finite"}
    )
    assert [item["id"] for item in search.json()] == [node["id"]]

    assert client.delete(
        f"/courses/{course['id']}/graph/nodes/{node['id']}"
    ).status_code == 204
    assert client.get(
        f"/courses/{course['id']}/graph/nodes/{node['id']}"
    ).status_code == 404
    assert client.get(f"/courses/{course['id']}/graph").json() == {"nodes": [], "edges": []}
    assert client.get(f"/courses/{course['id']}").json()["nodeCount"] == 0


def test_graph_relationship_lifecycle_neighbors_visualization_and_provenance(
    client: TestClient,
) -> None:
    course = create_course(client)
    document = upload_source(client, course["id"])
    source = create_node(client, course["id"], label="Line integrals")
    target = create_node(client, course["id"], label="Vector fields")
    response = client.post(
        f"/courses/{course['id']}/graph/relationships",
        json={
            "sourceNodeId": source["id"],
            "targetNodeId": target["id"],
            "type": "REQUIRES",
            "confidence": 0.75,
            "sourceDocumentId": document["id"],
            "sourceLocation": "section 2.1",
            "metadata": {"reviewed": True},
        },
    )
    assert response.status_code == 201, response.text
    relationship = response.json()
    assert relationship["sourceDocumentId"] == document["id"]
    assert relationship["sourceLocation"] == "section 2.1"

    retrieved = client.get(
        f"/courses/{course['id']}/graph/relationships/{relationship['id']}"
    )
    assert retrieved.json() == relationship
    updated = client.patch(
        f"/courses/{course['id']}/graph/relationships/{relationship['id']}",
        json={"confidence": 1, "type": "RELATED_TO"},
    )
    assert updated.status_code == 200
    assert updated.json()["confidence"] == 1
    assert updated.json()["type"] == "RELATED_TO"

    neighborhood = client.get(
        f"/courses/{course['id']}/graph/nodes/{source['id']}/neighbors"
    ).json()
    assert neighborhood["centerNodeId"] == source["id"]
    assert [node["id"] for node in neighborhood["nodes"]] == [target["id"]]
    assert [edge["id"] for edge in neighborhood["edges"]] == [relationship["id"]]
    visualization = client.get(f"/courses/{course['id']}/graph").json()
    assert {node["id"] for node in visualization["nodes"]} == {source["id"], target["id"]}
    assert [edge["id"] for edge in visualization["edges"]] == [relationship["id"]]

    assert client.delete(
        f"/courses/{course['id']}/graph/relationships/{relationship['id']}"
    ).status_code == 204
    assert client.get(
        f"/courses/{course['id']}/graph/relationships/{relationship['id']}"
    ).status_code == 404
    assert client.get(f"/courses/{course['id']}/graph").json()["edges"] == []


def test_graph_rejects_invalid_fields_and_references(client: TestClient) -> None:
    course = create_course(client)
    node = create_node(client, course["id"])
    invalid_payloads = [
        {"type": "UNKNOWN", "label": "Bad"},
        {"type": "CONCEPT", "label": "   "},
        {"type": "CONCEPT", "label": "Bad source", "sourceLocation": "page 1"},
        {"type": "CONCEPT", "label": "Bad document", "sourceDocumentId": "missing"},
    ]
    for payload in invalid_payloads:
        assert client.post(
            f"/courses/{course['id']}/graph/nodes", json=payload
        ).status_code == 422

    relationship_payloads = [
        {
            "sourceNodeId": node["id"],
            "targetNodeId": node["id"],
            "type": "RELATED_TO",
        },
        {
            "sourceNodeId": node["id"],
            "targetNodeId": "missing",
            "type": "RELATED_TO",
        },
        {
            "sourceNodeId": node["id"],
            "targetNodeId": "missing",
            "type": "INVALID",
            "confidence": 2,
        },
    ]
    for payload in relationship_payloads:
        assert client.post(
            f"/courses/{course['id']}/graph/relationships", json=payload
        ).status_code == 422
    assert client.patch(
        f"/courses/{course['id']}/graph/nodes/{node['id']}", json={}
    ).status_code == 422
    assert client.get(
        f"/courses/{course['id']}/graph/nodes/search", params={"q": " "}
    ).status_code == 422


def test_graph_missing_cross_course_and_duplicate_records(client: TestClient) -> None:
    first = create_course(client)
    second_response = client.post(
        "/courses", json={"name": "Topology", "code": "MATH330"}
    )
    second = second_response.json()
    first_document = upload_source(client, first["id"])
    first_node = create_node(client, first["id"])
    second_node = create_node(client, second["id"], label="Open sets")

    assert client.get(
        f"/courses/{second['id']}/graph/nodes/{first_node['id']}"
    ).status_code == 404
    assert client.get(
        f"/courses/{first['id']}/graph/nodes/missing"
    ).status_code == 404
    assert client.post(
        f"/courses/{second['id']}/graph/nodes",
        json={
            "type": "CONCEPT",
            "label": "Foreign source",
            "sourceDocumentId": first_document["id"],
        },
    ).status_code == 422
    assert client.post(
        f"/courses/{first['id']}/graph/relationships",
        json={
            "sourceNodeId": first_node["id"],
            "targetNodeId": second_node["id"],
            "type": "RELATED_TO",
        },
    ).status_code == 422
    assert client.post(
        f"/courses/{second['id']}/graph/relationships",
        json={
            "sourceNodeId": second_node["id"],
            "targetNodeId": create_node(client, second["id"], label="Closed sets")["id"],
            "type": "RELATED_TO",
            "sourceDocumentId": first_document["id"],
        },
    ).status_code == 422
    assert client.post(
        f"/courses/{first['id']}/graph/nodes",
        json={"type": "FORMULA", "label": first_node["label"]},
    ).status_code == 409

    other = create_node(client, first["id"], label="Linear maps")
    relationship_payload = {
        "sourceNodeId": first_node["id"],
        "targetNodeId": other["id"],
        "type": "RELATED_TO",
    }
    first_relationship = client.post(
        f"/courses/{first['id']}/graph/relationships", json=relationship_payload
    )
    assert first_relationship.status_code == 201
    assert client.post(
        f"/courses/{first['id']}/graph/relationships", json=relationship_payload
    ).status_code == 409
    assert client.get(
        f"/courses/{second['id']}/graph/relationships/{first_relationship.json()['id']}"
    ).status_code == 404
