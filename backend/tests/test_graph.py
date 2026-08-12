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


# --- Карта второго мозга (PR-20) ---


def _seed_map(client, node_count=3):
    for i in range(node_count):
        client.post("/api/graph/nodes", json={
            "id": f"n{i}", "label": f"Узел {i}", "node_type": "concept",
        })
    client.post("/api/graph/edges", json={"source": "n0", "target": "n1", "weight": 2})
    client.post("/api/graph/edges", json={"source": "n1", "target": "n2"})


def test_map_returns_nodes_edges_and_stats(client):
    _seed_map(client)

    data = client.get("/api/graph/map").json()

    assert [n["id"] for n in data["nodes"]] == ["n0", "n1", "n2"]
    assert {(e["source"], e["target"]) for e in data["edges"]} == {("n0", "n1"), ("n1", "n2")}
    assert data["stats"]["nodes"] == 3
    assert data["edges"][0]["weight"] == 2


def test_map_drops_edges_to_nodes_outside_the_limit(client):
    """Иначе карта рисует связь в пустоту — узла на холсте нет."""
    _seed_map(client)

    data = client.get("/api/graph/map", params={"limit": 2}).json()

    assert len(data["nodes"]) == 2
    assert {(e["source"], e["target"]) for e in data["edges"]} == {("n0", "n1")}


def test_empty_map_is_empty_not_broken(client):
    data = client.get("/api/graph/map").json()

    assert data["nodes"] == []
    assert data["edges"] == []


def test_edges_endpoint_lists_connections(client):
    _seed_map(client)

    edges = client.get("/api/graph/edges").json()

    assert len(edges) == 2
    assert edges[0]["edge_type"] == "related"
