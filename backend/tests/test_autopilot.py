"""Тесты автопилота Jarvis и его предохранителей (PR-10)."""
from datetime import datetime

import pytest

from backend.agents import autopilot
from backend.core.config import settings
from backend.services import budget


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(autopilot, "STATE_FILE", tmp_path / "autopilot_state.json")
    yield


def enable(monkeypatch, **overrides):
    monkeypatch.setattr(settings, "autopilot", True)
    monkeypatch.setattr(settings, "quiet_hours_start", 0)
    monkeypatch.setattr(settings, "quiet_hours_end", 0)  # тихих часов нет
    monkeypatch.setattr(settings, "jarvis_max_runs_per_day", 12)
    monkeypatch.setattr(settings, "daily_llm_budget_usd", 5.0)
    for key, value in overrides.items():
        monkeypatch.setattr(settings, key, value)


def test_autopilot_is_off_by_default():
    """Спека требует NEXUS_AUTOPILOT=off по умолчанию (риск R-2)."""
    assert settings.autopilot is False


def test_disabled_autopilot_reports_why(monkeypatch):
    monkeypatch.setattr(settings, "autopilot", False)
    assert "выключен" in autopilot.why_blocked()


def test_enabled_autopilot_is_not_blocked(monkeypatch):
    enable(monkeypatch)
    assert autopilot.why_blocked() is None


# --- Тихие часы ---


def test_quiet_hours_overnight(monkeypatch):
    monkeypatch.setattr(settings, "quiet_hours_start", 23)
    monkeypatch.setattr(settings, "quiet_hours_end", 8)

    assert autopilot.in_quiet_hours(datetime(2026, 8, 11, 23, 30))
    assert autopilot.in_quiet_hours(datetime(2026, 8, 11, 3, 0))
    assert not autopilot.in_quiet_hours(datetime(2026, 8, 11, 12, 0))


def test_quiet_hours_within_day(monkeypatch):
    monkeypatch.setattr(settings, "quiet_hours_start", 13)
    monkeypatch.setattr(settings, "quiet_hours_end", 15)

    assert autopilot.in_quiet_hours(datetime(2026, 8, 11, 14, 0))
    assert not autopilot.in_quiet_hours(datetime(2026, 8, 11, 16, 0))


def test_equal_bounds_mean_no_quiet_hours(monkeypatch):
    monkeypatch.setattr(settings, "quiet_hours_start", 0)
    monkeypatch.setattr(settings, "quiet_hours_end", 0)

    assert not autopilot.in_quiet_hours(datetime(2026, 8, 11, 3, 0))


@pytest.mark.asyncio
async def test_quiet_hours_stop_the_run(monkeypatch):
    enable(monkeypatch, quiet_hours_start=0, quiet_hours_end=23)

    result = await autopilot.tick()

    assert result["ran"] is False
    assert "тихие часы" in result["reason"]


# --- Дневной лимит ---


@pytest.mark.asyncio
async def test_daily_cap_stops_the_run(monkeypatch):
    enable(monkeypatch, jarvis_max_runs_per_day=0)

    result = await autopilot.tick()

    assert result["ran"] is False
    assert "лимит" in result["reason"]


def test_runs_are_counted(monkeypatch):
    assert autopilot.runs_today() == 0
    autopilot._count_run()
    autopilot._count_run()
    assert autopilot.runs_today() == 2


# --- Бюджет ---


@pytest.mark.asyncio
async def test_exhausted_budget_stops_the_run(monkeypatch):
    """Автопилот — фоновая нагрузка, бюджет обязан его глушить (I-4)."""
    enable(monkeypatch, daily_llm_budget_usd=0.0)
    monkeypatch.setattr(budget, "spent_today", lambda: 1.0)

    result = await autopilot.tick()

    assert result["ran"] is False
    assert "бюджет" in result["reason"].lower()


# --- Запуск ---


@pytest.mark.asyncio
async def test_missing_jarvis_agent_is_not_an_error(monkeypatch):
    enable(monkeypatch)

    result = await autopilot.tick()

    assert result["ran"] is False
    assert "Jarvis" in result["reason"]


@pytest.mark.asyncio
async def test_run_happens_when_all_clear(monkeypatch):
    from backend.models.schemas import AgentCreate, AgentRole
    from backend.services import agents as agent_svc

    enable(monkeypatch)
    agent_svc.create_agent(AgentCreate(name="Jarvis", role=AgentRole.JARVIS))

    calls = []

    def fake_run(agent_id, task, context):
        calls.append((agent_id, task, context))
        return {"status": "completed"}

    monkeypatch.setattr(agent_svc, "run_agent", fake_run)

    result = await autopilot.tick()

    assert result["ran"] is True
    assert result["run_number"] == 1
    # Прогон помечен как плановый — это важно для события agent.run_*
    assert calls[0][2]["trigger"] == "schedule"


@pytest.mark.asyncio
async def test_disabled_autopilot_does_not_count_runs(monkeypatch):
    monkeypatch.setattr(settings, "autopilot", False)

    await autopilot.tick()

    assert autopilot.runs_today() == 0


def test_status_explains_itself(monkeypatch):
    enable(monkeypatch)

    status = autopilot.status()

    assert status["enabled"] is True
    assert status["blocked_by"] is None
    assert status["max_runs_per_day"] == 12
