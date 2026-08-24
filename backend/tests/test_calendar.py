"""Calendar integration tests."""
import pytest

from backend.services import calendar as calendar_svc
from backend.services import google_auth


@pytest.fixture(autouse=True)
def google_disconnected(tmp_path, monkeypatch):
    """Календарь не подключён — что бы ни лежало на машине.

    Вход в Google общий с почтой и живёт в google_auth: пути к файлу
    доступа и токену там же. Без этой изоляции тесты ходили в настоящий
    календарь, а «создание события» создавало настоящую встречу.
    """
    monkeypatch.setattr(
        google_auth, "CREDENTIALS_PATHS", (tmp_path / "google_credentials.json",)
    )
    monkeypatch.setattr(google_auth, "TOKEN_FILE", tmp_path / "google_token.json")
    # Кэш событий модуль держит по своей копии DATA_DIR — иначе читали бы
    # и писали в реальный ~/.nexsys
    monkeypatch.setattr(calendar_svc, "DATA_DIR", tmp_path)
    return tmp_path


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


# --- Протухший токен ≠ «встреч нет» (23.08.2026) ---


def test_expired_token_raises_instead_of_pretending_calendar_is_empty(monkeypatch):
    """Фаундер смотрел на пустой экран и думал, что у него нет встреч, —
    а токен Google был отозван. `except Exception` глотал это и молча
    отдавал пустой кэш."""
    import pytest

    from backend.services import calendar as svc

    monkeypatch.setattr(svc, "is_configured", lambda: True)

    def boom(days, max_results):
        raise RuntimeError("('invalid_grant: Token has been expired or revoked.', {...})")

    monkeypatch.setattr(svc, "_fetch_from_api", boom)

    with pytest.raises(svc.CalendarAuthExpired):
        svc.get_upcoming_events()


def test_ordinary_failure_still_falls_back_to_cache(monkeypatch):
    """Сеть моргнула — ронять экран незачем, отдаём кэш как раньше."""
    from backend.services import calendar as svc

    monkeypatch.setattr(svc, "is_configured", lambda: True)
    monkeypatch.setattr(svc, "_read_cached_events", lambda: [{"summary": "из кэша"}])

    def boom(days, max_results):
        raise RuntimeError("Temporary failure in name resolution")

    monkeypatch.setattr(svc, "_fetch_from_api", boom)

    assert svc.get_upcoming_events() == [{"summary": "из кэша"}]


def test_api_reports_expired_token_as_503(client, monkeypatch):
    import backend.api.calendar as calendar_api

    def boom(days, max_results):
        raise calendar_api.svc.CalendarAuthExpired("Доступ отозван — войдите заново")

    monkeypatch.setattr(calendar_api.svc, "get_upcoming_events", boom)

    r = client.get("/api/calendar/events")

    assert r.status_code == 503
    assert "войдите заново" in r.json()["detail"]
