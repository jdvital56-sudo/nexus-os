"""Task service tests."""


def test_create_task(client):
    r = client.post("/api/tasks", json={
        "title": "Test Task",
        "description": "Do something",
        "priority": "high",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Test Task"
    assert data["priority"] == "high"
    assert data["status"] == "todo"


def test_list_tasks(client):
    client.post("/api/tasks", json={"title": "A"})
    client.post("/api/tasks", json={"title": "B"})
    r = client.get("/api/tasks")
    assert len(r.json()) == 2


def test_list_tasks_filter_status(client):
    client.post("/api/tasks", json={"title": "A", "status": "todo"})
    client.post("/api/tasks", json={"title": "B", "status": "done"})
    r = client.get("/api/tasks?status=done")
    assert len(r.json()) == 1


def test_update_task(client):
    r = client.post("/api/tasks", json={"title": "Old"})
    tid = r.json()["id"]
    r = client.patch(f"/api/tasks/{tid}", json={"status": "in_progress"})
    assert r.json()["status"] == "in_progress"


def test_delete_task(client):
    r = client.post("/api/tasks", json={"title": "Del"})
    tid = r.json()["id"]
    client.delete(f"/api/tasks/{tid}")
    r = client.get(f"/api/tasks/{tid}")
    assert r.status_code == 404
