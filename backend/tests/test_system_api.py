"""Сводка системы для дашборда (PR-17).

Главное требование к этим цифрам — они не выдуманы. Проверяем, что каждая
приходит из настоящего источника и меняется вместе с ним.
"""
from datetime import datetime, timezone

import pytest

from backend.services import budget, dream


def test_status_reports_real_spending(client, monkeypatch):
    monkeypatch.setattr(budget.settings, "daily_llm_budget_usd", 5.0)
    budget.record("deepseek-chat", {"prompt_tokens": 1_000_000, "completion_tokens": 0})

    spend = client.get("/api/system/status").json()["spend"]

    assert spend["spent_usd"] == pytest.approx(0.27)
    assert spend["budget_usd"] == 5.0
    assert spend["throttled"] is False


def test_status_shows_throttling(client, monkeypatch):
    monkeypatch.setattr(budget.settings, "daily_llm_budget_usd", 0.1)
    budget.record("deepseek-chat", {"prompt_tokens": 1_000_000, "completion_tokens": 0})

    assert client.get("/api/system/status").json()["spend"]["throttled"] is True


def test_spend_history_covers_every_day(client):
    history = client.get("/api/system/status").json()["spend"]["history"]

    assert len(history) == 14
    # Дни без вызовов — нули, а не пропуски: иначе на графике дыра
    assert all(day["spent_usd"] == 0.0 for day in history)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert history[-1]["date"] == today


def test_integrations_report_what_is_actually_configured(client, monkeypatch):
    monkeypatch.setattr(budget.settings, "telegram_bot_token", "")
    by_key = {i["key"]: i for i in client.get("/api/system/status").json()["integrations"]}

    assert by_key["telegram"]["connected"] is False
    assert "TELEGRAM_BOT_TOKEN" in by_key["telegram"]["detail"]

    monkeypatch.setattr(budget.settings, "telegram_bot_token", "123:ABC")
    by_key = {i["key"]: i for i in client.get("/api/system/status").json()["integrations"]}
    assert by_key["telegram"]["connected"] is True


def test_dream_block_is_empty_until_first_run(client):
    block = client.get("/api/system/status").json()["dream"]

    assert block["has_brief"] is False
    assert block["last_run_at"] is None
    assert block["new_findings"] == 0


def test_dream_block_follows_the_night_run(client):
    dream.save_brief("run-1", "утренний бриф", cost_usd=0.12, findings_count=2)
    dream.add_finding("run-1", "memory_hygiene", "Устаревший факт", "детали")

    block = client.get("/api/system/status").json()["dream"]

    assert block["has_brief"] is True
    assert block["last_run_id"] == "run-1"
    assert block["last_cost_usd"] == 0.12
    assert block["new_findings"] == 1


def test_autopilot_state_is_visible(client, monkeypatch):
    """Включённый Jarvis тратит деньги сам — это обязано быть видно (R-2)."""
    monkeypatch.setattr(budget.settings, "autopilot", False)
    assert client.get("/api/system/status").json()["autopilot"]["enabled"] is False

    monkeypatch.setattr(budget.settings, "autopilot", True)
    assert client.get("/api/system/status").json()["autopilot"]["enabled"] is True


def test_status_requires_token(client, temp_data_dir):
    """Сводка отдаёт состояние машины — с настроенным токеном она под замком."""
    from backend.core.jsonio import write_json

    write_json(temp_data_dir / "auth.json", {"token": "local-secret"})

    assert client.get("/api/system/status").status_code == 401
    assert client.get(
        "/api/system/status", headers={"Authorization": "Bearer wrong"}
    ).status_code == 401
    assert client.get(
        "/api/system/status", headers={"Authorization": "Bearer local-secret"}
    ).status_code == 200
