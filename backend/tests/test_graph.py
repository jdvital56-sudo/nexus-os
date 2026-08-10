"""Knowledge graph tests."""


def test_graph_stats(client):
    r = client.get("/api/graph/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["nodes"] == 0
    assert data["edges"] == 0


def test_add_node(client):
    r = client.post("/api/graph/nodes", json={
        "id": "n1",
        "label": "Test Node",
        "node_type": "concept",
    })
    assert r.status_code == 201
    assert r.json()["id"] == "n1"

    stats = client.get("/api/graph/stats").json()
    assert stats["nodes"] == 1


def test_add_edge(client):
    client.post("/api/graph/nodes", json={"id": "a", "label": "A", "node_type": "concept"})
    client.post("/api/graph/nodes", json={"id": "b", "label": "B", "node_type": "concept"})
    r = client.post("/api/graph/edges", json={
        "source": "a",
        "target": "b",
        "edge_type": "related",
    })
    assert r.status_code == 201
    stats = client.get("/api/graph/stats").json()
    assert stats["edges"] == 1


def test_add_edge_missing_node(client):
    client.post("/api/graph/nodes", json={"id": "a", "label": "A", "node_type": "concept"})
    r = client.post("/api/graph/edges", json={"source": "a", "target": "nonexistent"})
    assert r.status_code == 404


def test_remove_node(client):
    client.post("/api/graph/nodes", json={"id": "n1", "label": "X", "node_type": "concept"})
    r = client.delete("/api/graph/nodes/n1")
    assert r.status_code == 200
    stats = client.get("/api/graph/stats").json()
    assert stats["nodes"] == 0


def test_neighbors(client):
    client.post("/api/graph/nodes", json={"id": "a", "label": "A", "node_type": "concept"})
    client.post("/api/graph/nodes", json={"id": "b", "label": "B", "node_type": "concept"})
    client.post("/api/graph/nodes", json={"id": "c", "label": "C", "node_type": "concept"})
    client.post("/api/graph/edges", json={"source": "a", "target": "b"})
    client.post("/api/graph/edges", json={"source": "a", "target": "c"})
    r = client.get("/api/graph/neighbors/a")
    assert r.status_code == 200
    data = r.json()
    node_ids = {n["id"] for n in data["nodes"]}
    assert "a" in node_ids
    assert "b" in node_ids
    assert "c" in node_ids
    assert len(data["edges"]) == 2


def test_search(client):
    client.post("/api/graph/nodes", json={"id": "n1", "label": "Machine Learning", "node_type": "concept"})
    client.post("/api/graph/nodes", json={"id": "n2", "label": "Cooking Recipe", "node_type": "concept"})
    r = client.get("/api/graph/search?q=machine")
    assert len(r.json()) == 1
    assert r.json()[0]["label"] == "Machine Learning"
