"""Webhook endpoint tests."""


def test_webhook_basic(client):
    r = client.post("/api/webhooks", json={
        "source": "call",
        "title": "Call with client X",
        "content": "Discussed budget 300-500k. Next step: send proposal.",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["document_id"]
    assert len(data["tags"]) > 0
    assert data["graph_linked"] is True


def test_webhook_with_agent_trigger(client):
    # Create a librarian agent first
    client.post("/api/agents", json={"name": "Lib", "role": "librarian"})

    r = client.post("/api/webhooks", json={
        "source": "voice",
        "title": "Voice note",
        "content": "Reminder: call the client tomorrow about the contract",
        "trigger_agent": "librarian",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["agent_triggered"] == "librarian"


def test_webhook_batch(client):
    r = client.post("/api/webhooks/batch", json=[
        {"source": "email", "title": "Email 1", "content": "First email content"},
        {"source": "crm", "title": "CRM Event", "content": "New lead created"},
    ])
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 2


def test_webhook_sensitive_detection(client):
    r = client.post("/api/webhooks", json={
        "source": "email",
        "title": "Test",
        "content": "password=secret123 here are the credentials",
    })
    data = r.json()
    assert len(data["warnings"]) > 0
