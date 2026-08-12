"""Дневной потолок расходов на LLM (инвариант I-4).

Интерактивные запросы (Telegram, веб, голос) при превышении продолжают
работать с предупреждением — человек не должен упереться в тишину.
Фоновые (цикл Jarvis, Dream Cadence, извлечение сущностей) останавливаются
до полуночи UTC.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from ..core.config import DATA_DIR, ensure_data_dir, settings
from ..core.eventbus import SYSTEM_BUDGET as SYSTEM_BUDGET_EVENT
from ..core import eventbus
from ..core.jsonio import read_json, write_json

logger = logging.getLogger(__name__)

SPEND_FILE = DATA_DIR / "llm_spend.json"

# Вид вызова: фоновые глушим, интерактивные — нет
INTERACTIVE = "interactive"
BACKGROUND = "background"

# Цена за миллион токенов (вход, выход) в долларах.
# Локальные модели бесплатны; неизвестные считаем бесплатными и говорим об этом в логе.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-3-opus-20240229": (15.0, 75.0),
    "claude-3.5-sonnet": (3.0, 15.0),
    "gpt-4-turbo": (10.0, 30.0),
    "deepseek-chat": (0.27, 1.10),
    "gemini-2.0-flash": (0.10, 0.40),
}


class BudgetExceeded(RuntimeError):
    """Фоновый вызов отклонён: дневной бюджет исчерпан."""


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load() -> dict:
    ensure_data_dir()
    if SPEND_FILE.exists():
        return read_json(SPEND_FILE, {}) or {}
    return {}


def _save(data: dict) -> None:
    ensure_data_dir()
    write_json(SPEND_FILE, data)


def estimate_cost(model: str, usage: dict) -> float:
    """Считает стоимость вызова по токенам. Неизвестная модель — 0."""
    prices = PRICES_PER_MTOK.get(model)
    if not prices:
        return 0.0
    prompt_price, completion_price = prices
    prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    return (
        prompt_tokens * prompt_price + completion_tokens * completion_price
    ) / 1_000_000


def spent_today() -> float:
    """Сколько потрачено сегодня (UTC). Вчерашние записи не учитываются."""
    return float(_load().get(_today(), 0.0))


def budget_usd() -> float:
    return float(settings.daily_llm_budget_usd)


def record(model: str, usage: dict) -> float:
    """Добавляет стоимость вызова к сегодняшнему счётчику, возвращает её."""
    cost = estimate_cost(model, usage)
    if cost <= 0:
        return 0.0
    data = _load()
    today = _today()
    data[today] = round(float(data.get(today, 0.0)) + cost, 6)
    # Храним только последние 30 дней, чтобы файл не рос бесконечно
    for day in sorted(data)[:-30]:
        del data[day]
    _save(data)
    return cost


def check(kind: str = INTERACTIVE) -> bool:
    """Пускать ли вызов. Фоновый при превышении — нет (бросает BudgetExceeded).

    Возвращает True, если бюджет в порядке, и False, если интерактивный
    вызов идёт сверх лимита — вызывающий обязан предупредить пользователя.
    """
    budget = budget_usd()
    spent = spent_today()
    if spent < budget:
        return True

    # Предохранитель сработал — это обязано быть видно в Activity (I-6)
    eventbus.emit(SYSTEM_BUDGET_EVENT, status())

    if kind == BACKGROUND:
        raise BudgetExceeded(
            f"Дневной бюджет LLM исчерпан: ${spent:.2f} из ${budget:.2f}. "
            "Фоновые задачи остановлены до полуночи UTC."
        )
    logger.warning(
        "Дневной бюджет LLM превышен: $%.2f из $%.2f — интерактивный запрос пропущен",
        spent,
        budget,
    )
    return False


def history(days: int = 14) -> list[dict]:
    """Траты по дням, старые слева. Дни без вызовов показываем нулём —
    иначе на графике образуется дыра, и провал выглядит как пропуск данных."""
    data = _load()
    today = datetime.now(timezone.utc).date()
    out = []
    for back in range(days - 1, -1, -1):
        day = (today - timedelta(days=back)).strftime("%Y-%m-%d")
        out.append({"date": day, "spent_usd": round(float(data.get(day, 0.0)), 4)})
    return out


def status() -> dict:
    """Для события system.budget (контракт §3) и страницы затрат."""
    spent = spent_today()
    budget = budget_usd()
    return {
        "spent_usd": round(spent, 4),
        "budget_usd": budget,
        "throttled": spent >= budget,
    }
