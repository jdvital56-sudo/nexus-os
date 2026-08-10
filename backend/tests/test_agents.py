"""Agent service tests."""


def test_create_agent(client):
    r = client.post("/api/agents", json={
        "name": "TestBot",
        "role": "builder",
        "description": "A test agent",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "TestBot"
    assert data["role"] == "builder"
    assert data["status"] == "idle"


def test_list_agents(client):
    client.post("/api/agents", json={"name": "A", "role": "builder"})
    client.post("/api/agents", json={"name": "B", "role": "librarian"})
    r = client.get("/api/agents")
    assert len(r.json()) == 2


def test_list_agents_filter_role(client):
    client.post("/api/agents", json={"name": "A", "role": "builder"})
    client.post("/api/agents", json={"name": "B", "role": "librarian"})
    r = client.get("/api/agents?role=builder")
    assert len(r.json()) == 1


def test_update_agent(client):
    r = client.post("/api/agents", json={"name": "Old", "role": "builder"})
    aid = r.json()["id"]
    r = client.patch(f"/api/agents/{aid}", json={"name": "New"})
    assert r.json()["name"] == "New"


def test_delete_agent(client):
    r = client.post("/api/agents", json={"name": "Del", "role": "builder"})
    aid = r.json()["id"]
    client.delete(f"/api/agents/{aid}")
    r = client.get(f"/api/agents/{aid}")
    assert r.status_code == 404


def test_run_agent(client):
    r = client.post("/api/agents", json={"name": "Runner", "role": "reviewer"})
    aid = r.json()["id"]
    r = client.post(f"/api/agents/{aid}/run", json={"task": "review code", "context": {}})
    assert r.status_code == 200
    data = r.json()
    assert data["agent_id"] == aid
    assert data["status"] == "completed"
    assert "cycle complete" in data["output"].lower() or "not yet" in data["output"].lower()


def test_create_agent_invalid_role(client):
    r = client.post("/api/agents", json={"name": "Bad", "role": "nonexistent"})
    assert r.status_code == 422
