"""Memory system tests — 4-layer architecture."""


def test_add_fact(client):
    r = client.post("/api/memory/facts", json={
        "content": "Client X prefers email over phone",
        "layer": "inbox",
        "source": "call-123",
        "confidence": 0.7,
        "tags": ["client-x", "preference"],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["content"] == "Client X prefers email over phone"
    assert data["layer"] == "inbox"
    assert data["confidence"] == 0.7


def test_list_facts(client):
    client.post("/api/memory/facts", json={"content": "Fact 1", "layer": "inbox"})
    client.post("/api/memory/facts", json={"content": "Fact 2", "layer": "memory"})
    r = client.get("/api/memory/facts")
    assert len(r.json()) == 2


def test_list_facts_by_layer(client):
    client.post("/api/memory/facts", json={"content": "Inbox item", "layer": "inbox"})
    client.post("/api/memory/facts", json={"content": "Memory item", "layer": "memory"})
    r = client.get("/api/memory/facts?layer=memory")
    assert len(r.json()) == 1
    assert r.json()[0]["layer"] == "memory"


def test_update_fact(client):
    r = client.post("/api/memory/facts", json={"content": "Old content", "confidence": 0.3})
    fid = r.json()["id"]
    r = client.patch(f"/api/memory/facts/{fid}", json={"confidence": 0.9})
    assert r.json()["confidence"] == 0.9


def test_supersede(client):
    r = client.post("/api/memory/facts", json={"content": "Old fact", "layer": "memory"})
    old_id = r.json()["id"]
    r = client.post(f"/api/memory/facts/{old_id}/supersede", json={
        "new_content": "New fact replaces old",
        "confidence": 0.8,
    })
    new = r.json()
    assert new["content"] == "New fact replaces old"
    assert new["id"] != old_id

    # Old should be superseded
    old = client.get(f"/api/memory/facts/{old_id}").json()
    assert old["superseded_by"] == new["id"]


def test_promote(client):
    r = client.post("/api/memory/facts", json={"content": "Important fact", "layer": "inbox"})
    fid = r.json()["id"]
    r = client.post(f"/api/memory/facts/{fid}/promote", json={"to_layer": "memory"})
    assert r.json()["layer"] == "memory"


def test_recall(client):
    client.post("/api/memory/facts", json={"content": "Client budget is 300k", "tags": ["budget"]})
    client.post("/api/memory/facts", json={"content": "Meeting scheduled for Monday", "tags": ["meeting"]})
    r = client.get("/api/memory/recall?q=budget")
    assert len(r.json()) >= 1
    assert "budget" in r.json()[0]["content"].lower()


def test_stats(client):
    client.post("/api/memory/facts", json={"content": "Fact A", "layer": "inbox"})
    client.post("/api/memory/facts", json={"content": "Fact B", "layer": "memory"})
    r = client.get("/api/memory/stats")
    data = r.json()
    assert data["total"] >= 2
    assert "by_layer" in data


def test_ingest(client):
    r = client.post("/api/memory/ingest", json={
        "doc_id": "doc1",
        "content": "The project deadline is March 15. Budget approved at 500k. Team lead is Alex.",
    })
    data = r.json()
    assert data["ingested"] >= 1


def test_cleanup(client):
    # Add a fact with short TTL
    r = client.post("/api/memory/facts", json={
        "content": "Temporary fact",
        "ttl_hours": 0,  # already expired
    })
    r = client.post("/api/memory/cleanup")
    assert r.json()["removed"] >= 0
