"""Agent engine tests — real Orient-Observe-Think-Act-Verify cycle."""
from backend.models.schemas import AgentCreate, AgentRole, DocumentCreate, DocType


def test_librarian_cycle_empty(client):
    """Librarian on empty graph — should complete without errors."""
    # Create a librarian agent
    r = client.post("/api/agents", json={"name": "Lib", "role": "librarian"})
    agent_id = r.json()["id"]

    # Run cycle
    r = client.post(f"/api/agents/{agent_id}/run", json={"task": "organize graph", "context": {}})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert "Orient" in data["output"]
    assert "Verify" in data["output"]


def test_librarian_cycle_with_documents(client):
    """Librarian with unlinked documents — should link them to graph."""
    # Create agent
    r = client.post("/api/agents", json={"name": "Lib", "role": "librarian"})
    agent_id = r.json()["id"]

    # Create documents (auto-tagging happens automatically)
    client.post("/api/documents", json={
        "title": "Machine Learning Basics",
        "content": "Introduction to neural networks and deep learning algorithms",
    })
    client.post("/api/documents", json={
        "title": "Graph Database Design",
        "content": "How to design knowledge graphs with nodes and edges",
    })

    # Run librarian cycle
    r = client.post(f"/api/agents/{agent_id}/run", json={"task": "link documents", "context": {}})
    data = r.json()
    assert data["status"] == "completed"
    assert "linked" in data["output"].lower()

    # Verify graph has grown
    stats = client.get("/api/graph/stats").json()
    assert stats["nodes"] > 0  # document nodes + concept nodes


def test_reviewer_cycle(client):
    """Reviewer should check graph and create tasks for issues."""
    # Create reviewer
    r = client.post("/api/agents", json={"name": "QA", "role": "reviewer"})
    agent_id = r.json()["id"]

    # Add some nodes without connections (orphans)
    client.post("/api/graph/nodes", json={"id": "orphan1", "label": "Lonely Node", "node_type": "document"})

    # Run reviewer
    r = client.post(f"/api/agents/{agent_id}/run", json={"task": "check graph", "context": {}})
    data = r.json()
    assert data["status"] == "completed"
    assert "Orient" in data["output"]


def test_builder_cycle(client):
    """Builder role should execute a real cycle."""
    r = client.post("/api/agents", json={"name": "Build", "role": "builder"})
    agent_id = r.json()["id"]

    r = client.post(f"/api/agents/{agent_id}/run", json={"task": "build something", "context": {}})
    data = r.json()
    assert data["status"] == "completed"
    assert "builder" in data["output"].lower()
