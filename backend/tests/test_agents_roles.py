"""Test all 6 agent roles execute real cycles."""


def test_builder_cycle(client):
    r = client.post("/api/agents", json={"name": "Build", "role": "builder"})
    aid = r.json()["id"]
    r = client.post(f"/api/agents/{aid}/run", json={"task": "build feature"})
    data = r.json()
    assert data["status"] == "completed"
    assert "builder" in data["output"].lower()


def test_researcher_cycle(client):
    r = client.post("/api/agents", json={"name": "Research", "role": "researcher"})
    aid = r.json()["id"]
    # Add some sparse nodes
    client.post("/api/graph/nodes", json={"id": "sparse1", "label": "Sparse", "node_type": "concept"})
    r = client.post(f"/api/agents/{aid}/run", json={"task": "find gaps"})
    data = r.json()
    assert data["status"] == "completed"
    assert "research" in data["output"].lower()


def test_monitor_cycle(client):
    r = client.post("/api/agents", json={"name": "Watch", "role": "monitor"})
    aid = r.json()["id"]
    r = client.post(f"/api/agents/{aid}/run", json={"task": "check health"})
    data = r.json()
    assert data["status"] == "completed"
    assert "monitor" in data["output"].lower()


def test_jarvis_cycle(client):
    # Create some tasks
    client.post("/api/tasks", json={"title": "Urgent review", "priority": "high", "tags": ["review"]})
    client.post("/api/tasks", json={"title": "Build feature", "priority": "critical", "tags": ["build"]})

    r = client.post("/api/agents", json={"name": "Jarvis", "role": "jarvis"})
    aid = r.json()["id"]
    r = client.post(f"/api/agents/{aid}/run", json={"task": "orchestrate"})
    data = r.json()
    assert data["status"] == "completed"
    assert "jarvis" in data["output"].lower() or "orchestrat" in data["output"].lower()


def test_all_roles_exist(client):
    """All 6 roles should have working cycles."""
    roles = ["librarian", "reviewer", "builder", "researcher", "monitor", "jarvis"]
    for role in roles:
        r = client.post("/api/agents", json={"name": f"Test {role}", "role": role})
        assert r.status_code == 201, f"Failed to create {role} agent"
        aid = r.json()["id"]
        r = client.post(f"/api/agents/{aid}/run", json={"task": f"test {role}"})
        assert r.status_code == 200, f"Failed to run {role} agent"
        assert r.json()["status"] == "completed", f"{role} agent did not complete"
