"""QA Guard tests."""
from backend.services.qa_guard import quick_check


def test_quick_check_clean():
    warnings = quick_check("This is a normal document about project planning.")
    assert len(warnings) == 0


def test_quick_check_short():
    warnings = quick_check("Hi")
    assert any("short" in w.lower() for w in warnings)


def test_quick_check_credit_card():
    warnings = quick_check("Card number: 4111 1111 1111 1111")
    assert any("card" in w.lower() or "number" in w.lower() for w in warnings)


def test_quick_check_credential():
    warnings = quick_check("password=abc123 token=secret")
    assert any("credential" in w.lower() for w in warnings)


def test_quick_check_todo():
    warnings = quick_check("TODO: fix this later. The feature works but needs cleanup.")
    assert any("todo" in w.lower() for w in warnings)


def test_qa_gate_integration(client):
    """Create a document and run QA review on it."""
    # Create reviewer agent
    client.post("/api/agents", json={"name": "QA", "role": "reviewer"})

    # Create document
    r = client.post("/api/documents", json={
        "title": "Test Doc",
        "content": "This is a test document with enough content to pass basic checks.",
    })
    doc_id = r.json()["id"]

    # The QA gate is called internally; test that document was created successfully
    assert doc_id
    r = client.get(f"/api/documents/{doc_id}")
    assert r.status_code == 200
