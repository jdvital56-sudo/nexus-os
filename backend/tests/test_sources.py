"""Тесты библиотеки источников."""
from datetime import datetime, timedelta

import pytest

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.models.schemas import SourceCreate, SourceKind, SourceStatus, SourceUpdate
from backend.services import sources as svc


def _add(url="https://example.com/blog", **kw):
    return svc.add_source(SourceCreate(url=url, **kw))


# === Нормализация адреса ===


@pytest.mark.parametrize("raw,expected", [
    ("https://Example.COM/blog/", "https://example.com/blog"),
    ("https://example.com", "https://example.com"),
    ("https://example.com/a/b#anchor", "https://example.com/a/b"),
    ("  https://example.com/x  ", "https://example.com/x"),
    ("https://example.com/s?tag=ai", "https://example.com/s?tag=ai"),
])
def test_normalize_url(raw, expected):
    assert svc.normalize_url(raw) == expected


@pytest.mark.parametrize("bad", ["", "   ", "example.com", "ftp://example.com", "https://"])
def test_normalize_url_rejects_garbage(bad):
    with pytest.raises(ValidationError):
        svc.normalize_url(bad)


def test_query_string_makes_distinct_source():
    """Разные параметры — разные страницы, дублем считать нельзя."""
    _add("https://example.com/s?tag=ai")
    second = _add("https://example.com/s?tag=spa")
    assert second.id
    assert len(svc.list_sources()) == 2


# === CRUD ===


def test_add_and_get():
    src = _add(topics=["ai"], trust=0.8)
    assert src.url == "https://example.com/blog"
    assert src.topics == ["ai"]
    assert svc.get_source(src.id).trust == 0.8


def test_title_defaults_to_domain():
    assert _add("https://news.example.com/feed").title == "news.example.com"


def test_duplicate_rejected_after_normalization():
    _add("https://example.com/blog")
    with pytest.raises(ConflictError):
        _add("https://EXAMPLE.com/blog/")


def test_trust_is_clamped():
    assert _add("https://a.com", trust=5.0).trust == 1.0
    assert _add("https://b.com", trust=-3.0).trust == 0.0


def test_interval_below_one_hour_rejected():
    with pytest.raises(ValidationError):
        _add(check_interval_hours=0)


def test_update_fields():
    src = _add()
    updated = svc.update_source(src.id, SourceUpdate(title="Блог", topics=["spa"], trust=0.9))
    assert updated.title == "Блог"
    assert updated.topics == ["spa"]
    assert updated.trust == 0.9


def test_update_url_conflict():
    first = _add("https://a.com")
    second = _add("https://b.com")
    with pytest.raises(ConflictError):
        svc.update_source(second.id, SourceUpdate(url="https://a.com/"))
    # Исходный адрес остался нетронутым
    assert svc.get_source(second.id).url == "https://b.com"


def test_update_same_url_on_itself_is_allowed():
    src = _add("https://a.com")
    assert svc.update_source(src.id, SourceUpdate(url="https://A.com/")).url == "https://a.com"


def test_delete():
    src = _add()
    assert svc.delete_source(src.id) is True
    with pytest.raises(NotFoundError):
        svc.get_source(src.id)


def test_missing_source_raises():
    with pytest.raises(NotFoundError):
        svc.get_source("нет-такого")
    with pytest.raises(NotFoundError):
        svc.delete_source("нет-такого")
    with pytest.raises(NotFoundError):
        svc.record_check("нет-такого", ok=True)


# === Фильтры ===


def test_filters():
    _add("https://a.com", topics=["ai"], kind=SourceKind.RSS)
    _add("https://b.com", topics=["spa"], kind=SourceKind.SITE)
    disabled = _add("https://c.com", topics=["ai"])
    svc.update_source(disabled.id, SourceUpdate(enabled=False))

    assert len(svc.list_sources(topic="ai")) == 2
    assert len(svc.list_sources(kind="rss")) == 1
    assert len(svc.list_sources(topic="ai", enabled_only=True)) == 1


# === Очередь обхода ===


def test_never_checked_is_due():
    src = _add()
    assert [s.id for s in svc.due_sources()] == [src.id]


def test_recently_checked_is_not_due():
    src = _add(check_interval_hours=24)
    svc.record_check(src.id, ok=True)
    assert svc.due_sources() == []


def test_due_again_after_interval():
    src = _add(check_interval_hours=6)
    svc.record_check(src.id, ok=True)
    later = datetime.utcnow() + timedelta(hours=7)
    assert [s.id for s in svc.due_sources(now=later)] == [src.id]


def test_disabled_never_due():
    src = _add()
    svc.update_source(src.id, SourceUpdate(enabled=False))
    assert svc.due_sources() == []


def test_broken_timestamp_treated_as_never_checked():
    """Битую отметку времени нельзя молча ронять — источник просто в очередь."""
    src = _add()
    stored = svc._load()
    stored[0]["last_checked_at"] = "не-дата"
    svc._save(stored)
    assert [s.id for s in svc.due_sources()] == [src.id]


def test_never_checked_go_first():
    old = _add("https://a.com", check_interval_hours=1)
    svc.record_check(old.id, ok=True)
    fresh = _add("https://b.com")
    later = datetime.utcnow() + timedelta(hours=2)
    assert [s.id for s in svc.due_sources(now=later)] == [fresh.id, old.id]


# === Отметки обхода и карантин ===


def test_successful_check_accumulates_items():
    src = _add()
    svc.record_check(src.id, ok=True, items_found=3)
    after = svc.record_check(src.id, ok=True, items_found=2)
    assert after.items_found == 5
    assert after.check_count == 2
    assert after.last_status == SourceStatus.OK


def test_quarantine_after_error_streak():
    src = _add()
    for _ in range(svc.MAX_ERROR_STREAK):
        result = svc.record_check(src.id, ok=False, error="таймаут")
    assert result.error_streak == svc.MAX_ERROR_STREAK
    assert result.enabled is False
    assert result.last_error == "таймаут"


def test_success_resets_error_streak():
    src = _add()
    svc.record_check(src.id, ok=False, error="сбой")
    svc.record_check(src.id, ok=False, error="сбой")
    recovered = svc.record_check(src.id, ok=True)
    assert recovered.error_streak == 0
    assert recovered.enabled is True
    assert recovered.last_error == ""


def test_manual_enable_clears_quarantine():
    src = _add()
    for _ in range(svc.MAX_ERROR_STREAK):
        svc.record_check(src.id, ok=False, error="сбой")
    pardoned = svc.update_source(src.id, SourceUpdate(enabled=True))
    assert pardoned.enabled is True
    assert pardoned.error_streak == 0


# === Сводка ===


def test_stats():
    _add("https://a.com", topics=["ai"])
    checked = _add("https://b.com", topics=["spa"], check_interval_hours=24)
    svc.record_check(checked.id, ok=True)

    stats = svc.get_stats()
    assert stats["total"] == 2
    assert stats["enabled"] == 2
    assert stats["never_checked"] == 1
    assert stats["due_now"] == 1
    assert stats["topics"] == ["ai", "spa"]


# === Хранилище ===


def test_survives_reload_with_cyrillic():
    src = _add(title="Отраслевой блог", notes="Проверять по понедельникам")
    reloaded = svc.get_source(src.id)
    assert reloaded.title == "Отраслевой блог"
    assert reloaded.notes == "Проверять по понедельникам"


def test_storage_file_is_utf8(temp_data_dir):
    _add(title="Кириллица")
    raw = (temp_data_dir / "sources.json").read_text(encoding="utf-8")
    assert "Кириллица" in raw


# === API ===


def test_api_crud_roundtrip(client):
    created = client.post("/api/sources", json={"url": "https://example.com/blog", "topics": ["ai"]})
    assert created.status_code == 201
    source_id = created.json()["id"]

    assert client.get("/api/sources").status_code == 200
    assert client.get(f"/api/sources/{source_id}").json()["url"] == "https://example.com/blog"

    patched = client.patch(f"/api/sources/{source_id}", json={"title": "Блог"})
    assert patched.json()["title"] == "Блог"

    assert client.delete(f"/api/sources/{source_id}").json() == {"ok": True}
    assert client.get(f"/api/sources/{source_id}").status_code == 404


def test_api_duplicate_returns_409(client):
    payload = {"url": "https://example.com/blog"}
    client.post("/api/sources", json=payload)
    assert client.post("/api/sources", json={"url": "https://EXAMPLE.com/blog/"}).status_code == 409


def test_api_bad_url_returns_422(client):
    assert client.post("/api/sources", json={"url": "example.com"}).status_code == 422


def test_api_due_and_stats(client):
    client.post("/api/sources", json={"url": "https://example.com/blog"})
    assert len(client.get("/api/sources/due").json()) == 1
    assert client.get("/api/sources/stats").json()["total"] == 1
