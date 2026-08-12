"""Тесты дневного потолка расходов на LLM (I-4)."""
import pytest

from backend.services import budget


@pytest.fixture(autouse=True)
def spend_file(tmp_path, monkeypatch):
    """Счётчик расходов пишем в temp, чтобы не трогать реальные данные."""
    monkeypatch.setattr(budget, "SPEND_FILE", tmp_path / "llm_spend.json")
    yield


def set_budget(monkeypatch, value: float):
    monkeypatch.setattr(budget.settings, "daily_llm_budget_usd", value)


def test_known_model_cost_is_counted():
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 0}
    assert budget.estimate_cost("claude-3-opus-20240229", usage) == pytest.approx(15.0)


def test_unknown_model_is_free():
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}
    assert budget.estimate_cost("llama3.1:8b", usage) == 0.0


def test_anthropic_usage_field_names_are_understood():
    """Anthropic отдаёт input_tokens/output_tokens вместо prompt/completion."""
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    assert budget.estimate_cost("claude-3.5-sonnet", usage) == pytest.approx(3.0)


def test_record_accumulates_spend():
    budget.record("deepseek-chat", {"prompt_tokens": 1_000_000, "completion_tokens": 0})
    budget.record("deepseek-chat", {"prompt_tokens": 1_000_000, "completion_tokens": 0})
    assert budget.spent_today() == pytest.approx(0.54)


def test_interactive_call_passes_within_budget(monkeypatch):
    set_budget(monkeypatch, 5.0)
    assert budget.check(budget.INTERACTIVE) is True


def test_background_call_blocked_when_budget_is_zero(monkeypatch):
    set_budget(monkeypatch, 0.0)
    with pytest.raises(budget.BudgetExceeded):
        budget.check(budget.BACKGROUND)


def test_interactive_call_survives_zero_budget_with_warning(monkeypatch):
    """Человек в чате не должен упереться в тишину — только предупреждение."""
    set_budget(monkeypatch, 0.0)
    assert budget.check(budget.INTERACTIVE) is False


def test_background_blocked_after_spending_over_limit(monkeypatch):
    set_budget(monkeypatch, 1.0)
    budget.record("claude-3-opus-20240229", {"prompt_tokens": 100_000, "completion_tokens": 0})
    assert budget.spent_today() == pytest.approx(1.5)

    with pytest.raises(budget.BudgetExceeded):
        budget.check(budget.BACKGROUND)


def test_yesterday_spend_does_not_count(monkeypatch):
    set_budget(monkeypatch, 1.0)
    budget._save({"2020-01-01": 999.0})
    assert budget.spent_today() == 0.0
    assert budget.check(budget.BACKGROUND) is True


def test_status_reports_throttling(monkeypatch):
    set_budget(monkeypatch, 1.0)
    budget.record("claude-3-opus-20240229", {"prompt_tokens": 100_000, "completion_tokens": 0})

    status = budget.status()
    assert status["budget_usd"] == 1.0
    assert status["throttled"] is True
