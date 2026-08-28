from fastapi.testclient import TestClient


def create_course(client: TestClient) -> dict:
    response = client.post(
        "/courses",
        json={"name": "Vector Calculus", "code": "math221", "description": "Test course"},
    )
    assert response.status_code == 201
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
