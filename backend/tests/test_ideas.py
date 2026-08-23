"""Раздел «Идеи» — отдельно от задач (23.08.2026, спецификация фаундера)."""


def test_create_idea(client):
    r = client.post("/api/ideas", json={"content": "Голосовые уведомления о готовых задачах"})
    assert r.status_code == 201
    data = r.json()
    assert data["content"] == "Голосовые уведомления о готовых задачах"
    assert data["status"] == "new"
    assert data["source"] == "founder"


def test_create_idea_defaults_source_to_founder(client):
    r = client.post("/api/ideas", json={"content": "X"})
    assert r.json()["source"] == "founder"


def test_create_idea_system_source(client):
    r = client.post("/api/ideas", json={"content": "X", "source": "system"})
    assert r.json()["source"] == "system"


def test_list_ideas(client):
    client.post("/api/ideas", json={"content": "A"})
    client.post("/api/ideas", json={"content": "B"})
    r = client.get("/api/ideas")
    assert len(r.json()) == 2


def test_list_ideas_filters_by_status(client):
    r = client.post("/api/ideas", json={"content": "A"})
    iid = r.json()["id"]
    client.post("/api/ideas", json={"content": "B"})
    client.patch(f"/api/ideas/{iid}", json={"status": "planned"})

    r = client.get("/api/ideas?status=planned")
    assert len(r.json()) == 1
    assert r.json()[0]["content"] == "A"


def test_update_idea_status(client):
    r = client.post("/api/ideas", json={"content": "A"})
    iid = r.json()["id"]
    r = client.patch(f"/api/ideas/{iid}", json={"status": "dismissed"})
    assert r.json()["status"] == "dismissed"


def test_delete_idea(client):
    r = client.post("/api/ideas", json={"content": "A"})
    iid = r.json()["id"]
    client.delete(f"/api/ideas/{iid}")
    assert client.get(f"/api/ideas/{iid}").status_code == 404


def test_get_missing_idea_404(client):
    assert client.get("/api/ideas/нет-такого").status_code == 404


def test_ideas_are_separate_from_tasks(client):
    """Идея не должна всплывать в списке задач и наоборот."""
    client.post("/api/ideas", json={"content": "идея"})
    client.post("/api/tasks", json={"title": "задача"})

    assert len(client.get("/api/ideas").json()) == 1
    assert len(client.get("/api/tasks").json()) == 1


def test_propose_marks_source_as_system():
    from backend.services import ideas as svc

    idea = svc.propose("Автоматически предлагать голоса из свежих релизов edge-tts", context="разговор про TTS")
    assert idea.source.value == "system"
    assert idea.context == "разговор про TTS"
