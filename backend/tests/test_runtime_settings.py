"""Переключатели из интерфейса.

Раньше автопилот включался только переменной среды, которую читают при
старте: чтобы передумать, нужно было править .env и перезапускать бэкенд.
Кнопку так не сделать.
"""
import pytest

from backend.agents import autopilot
from backend.core.errors import ConflictError, NotFoundError
from backend.services import runtime_settings as rs
from backend.services import skills as skills_svc


# === Хранилище ===


def test_absent_key_returns_default():
    assert rs.get("нет-такого", "по умолчанию") == "по умолчанию"


def test_value_survives_reload():
    rs.set_value("ключ", {"вложенное": "значение"})
    assert rs.get("ключ") == {"вложенное": "значение"}


def test_clear_removes_override():
    rs.set_value("ключ", True)
    assert rs.clear("ключ") is True
    assert rs.get("ключ") is None


def test_clear_of_absent_key_is_harmless():
    assert rs.clear("нет-такого") is False


def test_broken_file_does_not_crash(temp_data_dir, monkeypatch):
    path = temp_data_dir / "runtime_settings.json"
    path.write_text("не json", encoding="utf-8")
    monkeypatch.setattr(rs, "SETTINGS_FILE", path)
    assert rs.all_overrides() == {}


# === Автопилот ===


def test_untouched_autopilot_follows_env():
    """Пока человек не решал — действует настройка из .env."""
    assert rs.autopilot_override() is None


@pytest.mark.parametrize("env_default", [True, False])
def test_button_beats_env(monkeypatch, env_default):
    from backend.core import config as cfg

    monkeypatch.setattr(cfg.settings, "autopilot", env_default)

    rs.set_autopilot(not env_default)
    assert autopilot.is_enabled() is (not env_default)


def test_turning_on_and_off(monkeypatch):
    rs.set_autopilot(True)
    assert autopilot.is_enabled() is True
    rs.set_autopilot(False)
    assert autopilot.is_enabled() is False


def test_clearing_override_returns_to_env(monkeypatch):
    from backend.core import config as cfg

    monkeypatch.setattr(cfg.settings, "autopilot", True)
    rs.set_autopilot(False)
    assert autopilot.is_enabled() is False

    rs.clear(rs.AUTOPILOT)
    assert autopilot.is_enabled() is True


def test_disabled_autopilot_reports_the_reason(monkeypatch):
    rs.set_autopilot(False)
    assert autopilot.why_blocked() == "автопилот выключен"


# === Скиллы ===


def test_skills_are_enabled_by_default():
    skills_svc.create_default_skills()
    assert all(s["enabled"] for s in skills_svc.list_skills())


def test_skill_can_be_turned_off_and_back():
    skills_svc.create_default_skills()

    skills_svc.set_enabled("publish-post", False)
    by_id = {s["id"]: s for s in skills_svc.list_skills()}
    assert by_id["publish-post"]["enabled"] is False

    skills_svc.set_enabled("publish-post", True)
    by_id = {s["id"]: s for s in skills_svc.list_skills()}
    assert by_id["publish-post"]["enabled"] is True


def test_turning_off_one_skill_leaves_others_alone():
    skills_svc.create_default_skills()
    skills_svc.set_enabled("publish-post", False)

    by_id = {s["id"]: s for s in skills_svc.list_skills()}
    assert by_id["reply-comment"]["enabled"] is True


def test_disabled_skill_refuses_to_run():
    """Иначе переключатель был бы украшением, а не запретом."""
    skills_svc.create_default_skills()
    skills_svc.set_enabled("publish-post", False)

    with pytest.raises(ConflictError):
        skills_svc.execute_skill("publish-post", {"topic": "AI", "platform": "twitter"})


def test_re_enabled_skill_runs_again():
    skills_svc.create_default_skills()
    skills_svc.set_enabled("publish-post", False)
    skills_svc.set_enabled("publish-post", True)

    result = skills_svc.execute_skill("publish-post", {"topic": "AI", "platform": "twitter"})
    assert result["steps_executed"] > 0


def test_turning_off_does_not_delete_the_contract(temp_data_dir):
    skills_svc.create_default_skills()
    skills_svc.set_enabled("publish-post", False)
    assert (temp_data_dir / "skills" / "publish-post.json").exists()


def test_toggling_unknown_skill_raises():
    with pytest.raises(FileNotFoundError):
        skills_svc.set_enabled("нет-такого", False)


def test_disabled_list():
    skills_svc.create_default_skills()
    skills_svc.set_enabled("publish-post", False)
    assert rs.disabled_skills() == ["publish-post"]


# === API ===


def test_api_autopilot_toggle(client):
    off = client.post("/api/system/autopilot", json={"enabled": False})
    assert off.status_code == 200
    assert off.json()["enabled"] is False
    assert off.json()["source"] == "кнопка"

    on = client.post("/api/system/autopilot", json={"enabled": True})
    assert on.json()["enabled"] is True

    assert client.get("/api/system/autopilot").json()["enabled"] is True


def test_api_autopilot_explains_why_blocked(client):
    client.post("/api/system/autopilot", json={"enabled": False})
    assert client.get("/api/system/autopilot").json()["blocked_by"] == "автопилот выключен"


def test_api_skill_toggle(client):
    skills_svc.create_default_skills()

    off = client.post("/api/skills/publish-post/enabled", json={"enabled": False})
    assert off.status_code == 200
    assert off.json()["enabled"] is False

    listed = {s["id"]: s for s in client.get("/api/skills").json()}
    assert listed["publish-post"]["enabled"] is False


def test_api_disabled_skill_run_returns_409(client):
    skills_svc.create_default_skills()
    client.post("/api/skills/publish-post/enabled", json={"enabled": False})

    run = client.post("/api/skills/publish-post/run", json={"params": {}})
    assert run.status_code == 409
