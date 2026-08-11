"""Тесты Пантеона и системного промпта Hermes (PR-8)."""
import pytest

from backend.agents.persona_manager import PersonaManager
from backend.services import personas as svc


def test_defaults_are_seeded_on_first_read():
    names = [p["name"] for p in svc.list_personas()]
    assert "Orpheus" in names
    assert "Architect" in names


def test_update_persists_to_disk():
    svc.update_persona("Architect", {"model": "claude-4-opus"})

    # Новое чтение — как будто процесс перезапустили
    assert svc.get_persona("Architect")["model"] == "claude-4-opus"


def test_update_survives_restart():
    """Файл на диске, а не состояние процесса (DoD)."""
    svc.update_persona("Orpheus", {"system_prompt": "Ты лаконичен."})
    svc.PERSONAS_FILE  # файл существует
    assert svc.PERSONAS_FILE.exists()

    reloaded = svc._load()
    orpheus = [p for p in reloaded["personas"] if p["name"] == "Orpheus"][0]
    assert orpheus["system_prompt"] == "Ты лаконичен."


def test_create_persona():
    created = svc.create_persona(
        {
            "name": "Ганимед",
            "description": "Ночные отчёты",
            "model": "deepseek-chat",
            "provider": "deepseek",
            "system_prompt": "Ты пишешь сухие отчёты.",
        }
    )

    assert created["name"] == "Ганимед"
    assert svc.get_persona("ганимед") is not None


def test_duplicate_persona_is_rejected():
    with pytest.raises(ValueError):
        svc.create_persona(
            {
                "name": "orpheus",
                "description": "дубль",
                "model": "x",
                "provider": "openai",
                "system_prompt": "y",
            }
        )


def test_missing_fields_are_rejected():
    with pytest.raises(ValueError):
        svc.create_persona({"name": "Пустая"})


def test_delete_persona():
    svc.delete_persona("Mercury")
    assert svc.get_persona("Mercury") is None


def test_cannot_delete_last_persona():
    for p in list(svc.list_personas())[:-1]:
        svc.delete_persona(p["name"])

    with pytest.raises(ValueError):
        svc.delete_persona(svc.list_personas()[0]["name"])


def test_system_prompt_has_default():
    assert "Nexus OS" in svc.get_system_prompt()


def test_system_prompt_is_editable_and_persists():
    svc.set_system_prompt("  Отвечай только по-русски.  ")

    assert svc.get_system_prompt() == "Отвечай только по-русски."
    assert svc._load()["system_prompt"] == "Отвечай только по-русски."


def test_empty_system_prompt_is_rejected():
    with pytest.raises(ValueError):
        svc.set_system_prompt("   ")


def test_reset_restores_pantheon():
    svc.delete_persona("Mercury")
    svc.set_system_prompt("что-то своё")

    svc.reset_to_defaults()

    assert svc.get_persona("Mercury") is not None
    assert "Nexus OS" in svc.get_system_prompt()


# --- PersonaManager читает то же хранилище ---


def test_manager_sees_api_changes():
    manager = PersonaManager()
    svc.update_persona("Architect", {"model": "новая-модель"})

    assert manager.get_persona("Architect")["model"] == "новая-модель"


def test_manager_sees_new_persona():
    manager = PersonaManager()
    svc.create_persona(
        {
            "name": "Веста",
            "description": "тест",
            "model": "m",
            "provider": "openai",
            "system_prompt": "p",
        }
    )

    assert manager.get_persona("Веста") is not None


def test_manager_survives_deleted_default_persona():
    """Удалили Orpheus — автоопределение не должно падать."""
    manager = PersonaManager()
    svc.delete_persona("Orpheus")

    persona = manager.detect_persona("просто болтовня без ключевых слов")

    assert persona is not None
    assert persona["name"] != "Orpheus"


def test_custom_personas_do_not_touch_storage():
    """Тестовый список остаётся в памяти — хранилище не портим."""
    manager = PersonaManager(custom_personas=[
        {"name": "Только", "description": "d", "model": "m", "provider": "openai", "system_prompt": "s"}
    ])

    assert [p["name"] for p in manager.list_personas()] == ["Только"]
    assert svc.get_persona("Orpheus") is not None


# --- HTTP API ---


def test_api_lists_personas(client):
    r = client.get("/api/personas")
    assert r.status_code == 200
    assert any(p["name"] == "Orpheus" for p in r.json())


def test_api_updates_persona(client):
    r = client.put("/api/personas/Architect", json={"model": "claude-4-sonnet"})
    assert r.status_code == 200
    assert r.json()["model"] == "claude-4-sonnet"
    assert svc.get_persona("Architect")["model"] == "claude-4-sonnet"


def test_api_unknown_persona_is_404(client):
    assert client.get("/api/personas/Выдуманная").status_code == 404


def test_api_system_prompt_roundtrip(client):
    r = client.put("/api/personas/system-prompt", json={"system_prompt": "Будь краток."})
    assert r.status_code == 200

    assert client.get("/api/personas/system-prompt").json()["system_prompt"] == "Будь краток."


def test_api_rejects_empty_system_prompt(client):
    assert client.put("/api/personas/system-prompt", json={"system_prompt": " "}).status_code == 400


def test_api_creates_and_deletes(client):
    payload = {
        "name": "Церера",
        "description": "d",
        "model": "m",
        "provider": "openai",
        "system_prompt": "s",
    }
    assert client.post("/api/personas", json=payload).status_code == 201
    assert client.delete("/api/personas/Церера").status_code == 200
    assert svc.get_persona("Церера") is None
