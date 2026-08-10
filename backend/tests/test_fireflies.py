"""Fireflies integration tests."""


def test_parse_transcript(client):
    r = client.post("/api/fireflies/parse", json={
        "text": "[10:00] Alex: Привет, обсудим бюджет.\n[10:01] Maria: Нужно выделить 300к на проект.\n[10:02] Alex: Договорились, 300к утверждено.",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["speaker_count"] == 2
    assert "Alex" in data["speakers"]
    assert "Maria" in data["speakers"]
    assert len(data["decisions"]) >= 1


def test_ingest_transcript(client):
    r = client.post("/api/fireflies/transcript", json={
        "text": "[10:00] Alex: Привет, обсудим сроки.\n[10:01] Maria: Нужно сделать до пятницы.\n[10:02] Alex: Договорились, пятница дедлайн.",
        "title": "Planning Call",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["document_id"]
    assert data["call_id"]
    assert data["memory_facts_created"] >= 1
    assert len(data["participants"]) >= 2

    # Check document was created
    doc = client.get(f"/api/documents/{data['document_id']}")
    assert doc.status_code == 200

    # Check graph has call node
    stats = client.get("/api/graph/stats").json()
    assert stats["nodes"] > 0


def test_ingest_with_action_items(client):
    r = client.post("/api/fireflies/transcript", json={
        "text": "Alex: Нужно отправить КП клиенту.\nMaria: Сделаю до вечера.\nAlex: Надо также позвонить поставщику.",
    })
    data = r.json()
    assert data["tasks_created"] >= 1


def test_call_history(client):
    client.post("/api/fireflies/transcript", json={
        "text": "Alex: Hello\nMaria: Hi",
        "title": "Quick Call",
    })
    r = client.get("/api/fireflies/history")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_call_history_by_person(client):
    client.post("/api/fireflies/transcript", json={
        "text": "Alice: Hi\nBob: Hello",
        "title": "Meeting 1",
    })
    client.post("/api/fireflies/transcript", json={
        "text": "Charlie: Hey\nAlice: What's up",
        "title": "Meeting 2",
    })
    r = client.get("/api/fireflies/history?person=Alice")
    data = r.json()
    assert len(data) >= 2
