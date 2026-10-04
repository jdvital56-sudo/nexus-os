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
    # Модель с фиксированной ценой: у DeepSeek цена зависит от часа суток,
    # и тест на накопление не должен падать ночью и проходить днём.
    budget.record("claude-3.5-sonnet", {"input_tokens": 1_000_000, "output_tokens": 0})
    budget.record("claude-3.5-sonnet", {"input_tokens": 1_000_000, "output_tokens": 0})
    assert budget.spent_today() == pytest.approx(6.0)


# --- DeepSeek: кэш и часы пик (найдено сверкой с консолью 24.09.2026) ----

from datetime import datetime, timezone

PEAK = datetime(2026, 9, 24, 7, 0, tzinfo=timezone.utc)      # четверг, 07:00 UTC — пик
OFF_PEAK = datetime(2026, 9, 24, 14, 0, tzinfo=timezone.utc)  # четверг, 14:00 UTC
WEEKEND = datetime(2026, 9, 26, 7, 0, tzinfo=timezone.utc)    # суббота


def test_deepseek_cache_hits_are_nearly_free():
    """Фаундер поймал: моя оценка $1.45 против $0.26 в консоли. Весь вход
    считался по полной цене, а почти весь он шёл из кэша."""
    usage = {"prompt_tokens": 1_000_000, "prompt_cache_hit_tokens": 1_000_000,
             "prompt_cache_miss_tokens": 0, "completion_tokens": 0}
    assert budget.estimate_cost("deepseek-flash", usage, now=PEAK) == pytest.approx(0.006)


def test_deepseek_cache_miss_is_full_price():
    """Обратная сторона: то, что мимо кэша, по-прежнему стоит свои деньги."""
    usage = {"prompt_tokens": 1_000_000, "prompt_cache_hit_tokens": 0,
             "prompt_cache_miss_tokens": 1_000_000, "completion_tokens": 1_000_000}
    assert budget.estimate_cost("deepseek-flash", usage, now=PEAK) == pytest.approx(0.30 + 1.20)


def test_deepseek_off_peak_and_weekend_are_half_price():
    usage = {"prompt_tokens": 0, "prompt_cache_miss_tokens": 1_000_000, "completion_tokens": 0}
    assert budget.estimate_cost("deepseek-flash", usage, now=OFF_PEAK) == pytest.approx(0.15)
    assert budget.estimate_cost("deepseek-flash", usage, now=WEEKEND) == pytest.approx(0.15)


def test_deepseek_without_breakdown_is_counted_conservatively():
    """Разбивки кэша нет — считаем всё мимо кэша: переоценить безопаснее."""
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 0}
    assert budget.estimate_cost("deepseek-flash", usage, now=PEAK) == pytest.approx(0.30)


def test_estimate_matches_the_founders_console_order_of_magnitude():
    """Сверка с консолью: 5,54 млн токенов за месяц — $0.26.

    Агент повторяет промпт роли на каждом шаге, поэтому около 90% входа —
    из кэша. Старая формула дала бы около $1.5; новая обязана попасть в
    порядок консоли, а не в порядок старой ошибки.
    """
    usage = {"prompt_tokens": 5_390_000, "prompt_cache_hit_tokens": 4_850_000,
             "prompt_cache_miss_tokens": 540_000, "completion_tokens": 150_000}
    cost = budget.estimate_cost("deepseek-flash", usage, now=PEAK)
    assert 0.1 < cost < 0.4, f"оценка {cost:.3f} не в порядке консоли ($0.26)"


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
