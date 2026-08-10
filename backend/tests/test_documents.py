"""Document service tests."""
from backend.models.schemas import DocumentCreate, DocType


def test_create_document(client):
    r = client.post("/api/documents", json={
        "title": "Test Doc",
        "content": "Hello world",
        "doc_type": "markdown",
        "tags": ["test"],
    })
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Test Doc"
    assert data["doc_type"] == "markdown"
    assert "test" in data["tags"]
    assert "id" in data


def test_list_documents(client):
    client.post("/api/documents", json={"title": "A", "content": "a"})
    client.post("/api/documents", json={"title": "B", "content": "b", "tags": ["x"]})
    r = client.get("/api/documents")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_list_documents_filter_tag(client):
    client.post("/api/documents", json={"title": "A", "content": "a", "tags": ["keep"]})
    client.post("/api/documents", json={"title": "B", "content": "b", "tags": ["other"]})
    r = client.get("/api/documents?tag=keep")
    assert len(r.json()) == 1
    assert r.json()[0]["title"] == "A"


def test_get_document(client):
    r = client.post("/api/documents", json={"title": "X", "content": "x"})
    doc_id = r.json()["id"]
    r = client.get(f"/api/documents/{doc_id}")
    assert r.status_code == 200
    assert r.json()["title"] == "X"


def test_get_document_not_found(client):
    r = client.get("/api/documents/nonexistent")
    assert r.status_code == 404
    assert r.json()["code"] == "NOT_FOUND"


def test_update_document(client):
    r = client.post("/api/documents", json={"title": "Old", "content": "old"})
    doc_id = r.json()["id"]
    r = client.patch(f"/api/documents/{doc_id}", json={"title": "New"})
    assert r.status_code == 200
    assert r.json()["title"] == "New"
    assert r.json()["content"] == "old"  # unchanged


def test_delete_document(client):
    r = client.post("/api/documents", json={"title": "Del", "content": "del"})
    doc_id = r.json()["id"]
    r = client.delete(f"/api/documents/{doc_id}")
    assert r.status_code == 200
    r = client.get(f"/api/documents/{doc_id}")
    assert r.status_code == 404
