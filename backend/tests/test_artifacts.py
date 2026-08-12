"""Тесты единой папки артефактов (PR-14)."""
import pytest

from backend.services import artifacts


def test_kebab_case_filename():
    assert artifacts.slugify("Утренний Бриф   2026") == "утренний-бриф-2026"
    assert artifacts.slugify("Report: Q1/Q2 (draft)") == "report-q1q2-draft"


def test_empty_title_still_gives_a_name():
    assert artifacts.slugify("!!!") == "artifact"


def test_saved_artifact_has_kebab_filename():
    item = artifacts.save("Коммерческое Предложение", "текст", description="КП для клиента")

    assert item["filename"].endswith("-коммерческое-предложение.md")
    assert (artifacts.artifacts_dir() / item["filename"]).is_file()


def test_description_is_mandatory():
    """Файл без описания через месяц — мусор, который страшно удалить."""
    with pytest.raises(ValueError) as e:
        artifacts.save("Заголовок", "текст", description="   ")

    assert "описание" in str(e.value)


def test_title_is_mandatory():
    with pytest.raises(ValueError):
        artifacts.save("  ", "текст", description="есть описание")


def test_same_title_does_not_overwrite():
    first = artifacts.save("Отчёт", "первый", description="раз")
    second = artifacts.save("Отчёт", "второй", description="два")

    assert first["filename"] != second["filename"]
    assert artifacts.read_artifact(first["id"]) == "первый"
    assert artifacts.read_artifact(second["id"]) == "второй"


def test_content_can_be_read_back():
    item = artifacts.save("Заметка", "содержимое файла", description="тест")

    assert artifacts.read_artifact(item["id"]) == "содержимое файла"


def test_listing_is_newest_first():
    artifacts.save("Первый", "a", description="d")
    artifacts.save("Второй", "b", description="d")

    assert [i["title"] for i in artifacts.list_artifacts()][0] == "Второй"


def test_filter_by_kind():
    artifacts.save("Бриф", "a", description="d", kind="brief")
    artifacts.save("Документ", "b", description="d", kind="document")

    assert [i["title"] for i in artifacts.list_artifacts(kind="brief")] == ["Бриф"]


# --- Удаление только человеком (хартия §6, п.3) ---


def test_delete_without_confirmation_is_refused():
    item = artifacts.save("Важный файл", "данные", description="нужен")

    with pytest.raises(PermissionError) as e:
        artifacts.delete(item["id"])

    assert "подтверждения" in str(e.value)
    assert (artifacts.artifacts_dir() / item["filename"]).is_file()


def test_confirmed_delete_removes_file():
    item = artifacts.save("Черновик", "данные", description="не нужен")

    result = artifacts.delete(item["id"], confirmed=True)

    assert result["deleted"] is True
    assert not (artifacts.artifacts_dir() / item["filename"]).exists()


def test_request_delete_keeps_the_file():
    """Система помечает, но не стирает — решает человек."""
    item = artifacts.save("Спорный", "данные", description="возможно не нужен")

    marked = artifacts.request_delete(item["id"], reason="дубликат")

    assert marked["status"] == artifacts.STATUS_PENDING_DELETE
    assert marked["delete_reason"] == "дубликат"
    assert (artifacts.artifacts_dir() / item["filename"]).is_file()


def test_delete_request_can_be_cancelled():
    item = artifacts.save("Передумал", "данные", description="d")
    artifacts.request_delete(item["id"])

    restored = artifacts.cancel_delete(item["id"])

    assert restored["status"] == artifacts.STATUS_ACTIVE
    assert restored["delete_requested_at"] is None


# --- Файлы мимо реестра ---


def test_orphan_files_are_adopted_honestly():
    stray = artifacts.artifacts_dir() / "случайный-файл.md"
    stray.write_text("что-то", encoding="utf-8")

    adopted = artifacts.adopt_orphans()

    assert len(adopted) == 1
    assert adopted[0]["kind"] == "unknown"
    assert "неизвестно" in adopted[0]["description"]


def test_temp_files_are_not_artifacts():
    """Скачанные голосовые — мусор процесса, в реестр не попадают."""
    (artifacts.temp_dir() / "voice_1.ogg").write_bytes(b"audio")

    artifacts.adopt_orphans()

    assert artifacts.list_artifacts() == []


# --- HTTP API ---


def test_api_create_and_read(client):
    created = client.post("/api/artifacts", json={
        "title": "План на неделю", "content": "текст плана",
        "description": "что делаем с понедельника",
    })
    assert created.status_code == 201
    aid = created.json()["id"]

    assert client.get(f"/api/artifacts/{aid}/content").json()["content"] == "текст плана"


def test_api_rejects_artifact_without_description(client):
    r = client.post("/api/artifacts", json={
        "title": "Без описания", "content": "текст", "description": "",
    })
    assert r.status_code == 400


def test_api_delete_needs_confirmation(client):
    aid = client.post("/api/artifacts", json={
        "title": "Файл", "content": "x", "description": "d",
    }).json()["id"]

    assert client.delete(f"/api/artifacts/{aid}").status_code == 403
    assert client.delete(f"/api/artifacts/{aid}?confirmed=true").status_code == 200
