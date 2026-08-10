"""Calendar integration tests."""


def test_calendar_status(client):
    r = client.get("/api/calendar/status")
    assert r.status_code == 200
    data = r.json()
    assert "configured" in data


def test_calendar_events_empty(client):
    """Without credentials, should return empty list."""
    r = client.get("/api/calendar/events")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 0
    assert data["events"] == []


def test_calendar_sync_empty(client):
    r = client.post("/api/calendar/sync")
    assert r.status_code == 200
    data = r.json()
    assert data["events_synced"] == 0


def test_calendar_create_event_no_credentials(client):
    r = client.post("/api/calendar/create-event", json={
        "title": "Test Meeting",
        "description": "Discuss project",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["created"] is False
