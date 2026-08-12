"""Автопилот: цикл Jarvis по расписанию.

Ставится последним и по умолчанию выключен. Порядок из спецификации не
случаен: сначала должна неделю поработать гигиена памяти (PR-11), иначе
автономный цикл начнёт наполнять INBOX быстрее, чем его разбирают —
это риск R-2. Включает человек, руками, осознанно.

Четыре предохранителя, любой из которых останавливает прогон:
выключатель, тихие часы, дневной лимит прогонов и бюджет (I-4).
"""
import logging
from datetime import datetime, timezone

from ..core.config import DATA_DIR, ensure_data_dir, settings
from ..core.jsonio import read_json, write_json
from ..services import budget

logger = logging.getLogger(__name__)

STATE_FILE = DATA_DIR / "autopilot_state.json"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load() -> dict:
    ensure_data_dir()
    return read_json(STATE_FILE, {}) or {}


def runs_today() -> int:
    return int(_load().get(_today(), 0))


def _count_run() -> int:
    data = _load()
    today = _today()
    data[today] = runs_today() + 1
    # Держим только последнюю неделю
    for day in sorted(data)[:-7]:
        del data[day]
    ensure_data_dir()
    write_json(STATE_FILE, data)
    return data[today]


def is_enabled() -> bool:
    """Решение человека из интерфейса сильнее переменной среды.

    Переменная — позиция по умолчанию при старте, нажатие кнопки —
    сегодняшнее решение. Иначе автопилот нельзя было бы выключить, не
    правя .env и не перезапуская бэкенд.
    """
    from ..services import runtime_settings

    override = runtime_settings.autopilot_override()
    if override is not None:
        return override
    return bool(settings.autopilot)


def in_quiet_hours(now: datetime | None = None) -> bool:
    """Тихие часы — когда фаундер спит и не должен получать шевеления."""
    start, end = settings.quiet_hours_start, settings.quiet_hours_end
    if start == end:
        return False
    hour = (now or datetime.now()).hour
    if start < end:
        return start <= hour < end
    # Интервал через полночь, например 23-8
    return hour >= start or hour < end


def why_blocked() -> str | None:
    """Что мешает прогону прямо сейчас. None — можно работать."""
    if not is_enabled():
        return "автопилот выключен"
    if in_quiet_hours():
        return f"тихие часы {settings.quiet_hours_start}:00–{settings.quiet_hours_end}:00"
    if runs_today() >= settings.jarvis_max_runs_per_day:
        return f"дневной лимит прогонов исчерпан ({settings.jarvis_max_runs_per_day})"
    try:
        budget.check(budget.BACKGROUND)
    except budget.BudgetExceeded as e:
        return str(e)
    return None


async def tick() -> dict:
    """Один тик автопилота. Возвращает, что произошло."""
    blocked = why_blocked()
    if blocked:
        logger.info("Автопилот пропускает прогон: %s", blocked)
        return {"ran": False, "reason": blocked}

    from ..models.schemas import AgentRole
    from ..services import agents as agent_svc

    jarvis = next(
        (a for a in agent_svc.list_agents() if a.role == AgentRole.JARVIS), None
    )
    if not jarvis:
        logger.info("Автопилот: агент Jarvis не заведён — нечего запускать")
        return {"ran": False, "reason": "агент Jarvis не найден"}

    import asyncio

    number = _count_run()
    logger.info("Автопилот: прогон %s (%d за сегодня)", jarvis.id, number)
    result = await asyncio.to_thread(
        agent_svc.run_agent,
        jarvis.id,
        "Плановый осмотр системы",
        {"trigger": "schedule"},
    )
    return {"ran": True, "run_number": number, "result": result}


def status() -> dict:
    """Для экрана и для /status в боте."""
    return {
        "enabled": is_enabled(),
        "interval_min": settings.jarvis_interval_min,
        "runs_today": runs_today(),
        "max_runs_per_day": settings.jarvis_max_runs_per_day,
        "quiet_hours": f"{settings.quiet_hours_start}:00–{settings.quiet_hours_end}:00",
        "blocked_by": why_blocked(),
    }
