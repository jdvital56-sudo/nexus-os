"""Vector store tests."""


def test_vector_stats(client):
    r = client.get("/api/vectors/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total_vectors" in data
    assert "embedding_model" in data


def test_vector_add_and_search(client):
    # Add vectors (may fall back to text search if no model)
    client.post("/api/vectors", json={"id": "v1", "text": "Machine learning is a branch of AI", "metadata": {"topic": "ml"}})
    client.post("/api/vectors", json={"id": "v2", "text": "Cooking pasta with tomato sauce", "metadata": {"topic": "food"}})
    client.post("/api/vectors", json={"id": "v3", "text": "Deep learning neural networks for AI", "metadata": {"topic": "dl"}})

    # Search — text search matches on word overlap
    r = client.get("/api/vectors/search?q=machine+learning+AI")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 1


def test_vector_delete(client):
    client.post("/api/vectors", json={"id": "del1", "text": "to be deleted"})
    r = client.delete("/api/vectors/del1")
    assert r.json()["ok"] is True


def test_vector_sync_memory(client):
    # Add memory facts
    client.post("/api/memory/facts", json={"content": "Budget is 300k", "layer": "memory"})
    client.post("/api/memory/facts", json={"content": "Client prefers email", "layer": "operational"})

    r = client.post("/api/vectors/sync/memory")
    assert r.status_code == 200
    assert "synced" in r.json()


def test_vector_sync_documents(client):
    client.post("/api/documents", json={"title": "AI Guide", "content": "Introduction to artificial intelligence"})
    r = client.post("/api/vectors/sync/documents")
    assert r.status_code == 200
    assert "synced" in r.json()
