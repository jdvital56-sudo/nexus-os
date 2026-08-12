"""System API — сводка для дашборда (PR-17).

Дашборд до этого показывал придуманные числа: «сэкономлено $8940», «ROI
3512%». Их никто не считал, они были вписаны в код руками. Здесь только то,
что система знает на самом деле: сколько потрачено, что подключено, когда
был ночной прогон. Чего система не знает — того тут нет.
"""
import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..core.auth import get_token_dep
from ..core.config import settings
from ..services import budget, dream, obsidian

router = APIRouter(prefix="/api/system", tags=["system"])
auth = get_token_dep()


def _integrations() -> list[dict]:
    """Что действительно настроено. Проверяем ключ или файл, а не намерение."""
    calendar_ready = os.path.exists("credentials.json")
    voice_key = settings.gemini_api_key

    return [
        {
            "key": "telegram",
            "label": "Telegram (Hermes)",
            "connected": bool(settings.telegram_bot_token),
            "detail": "бот отвечает в чате" if settings.telegram_bot_token else "нет TELEGRAM_BOT_TOKEN",
        },
        {
            "key": "llm",
            "label": "Модель по умолчанию",
            "connected": bool(settings.llm_api_key or settings.llm_provider == "ollama"),
            "detail": f"{settings.llm_provider}/{settings.llm_model}",
        },
        {
            "key": "obsidian",
            "label": "База знаний Obsidian",
            "connected": obsidian.is_configured(),
            "detail": settings.obsidian_vault_path or "нет OBSIDIAN_VAULT_PATH",
        },
        {
            "key": "voice",
            "label": "Расшифровка голоса",
            "connected": bool(voice_key),
            "detail": "Gemini" if voice_key else "нет ключа Gemini — голосовые не расшифровываются",
        },
        {
            "key": "calendar",
            "label": "Google Calendar",
            "connected": calendar_ready,
            "detail": "credentials.json на месте" if calendar_ready else "нет credentials.json",
        },
        {
            "key": "apollo",
            "label": "Apollo.io",
            "connected": bool(settings.apollo_api_key),
            "detail": "поиск компаний" if settings.apollo_api_key else "нет ключа",
        },
    ]


def _dream() -> dict:
    """Ночной прогон: когда был, что принёс, сколько стоил."""
    brief = dream.get_brief()
    new_findings = len(dream.list_findings(status=dream.STATUS_NEW))
    return {
        "cron": os.getenv("NIGHT_ANALYSIS_CRON", "0 3 * * *"),
        "last_run_at": (brief or {}).get("created_at"),
        "last_run_id": (brief or {}).get("run_id"),
        "last_cost_usd": (brief or {}).get("cost_usd"),
        "has_brief": brief is not None,
        "new_findings": new_findings,
    }


def _runtime() -> dict:
    """Где что лежит и кто ведёт расписание.

    Экран настроек показывал это зашитым в код текстом — то есть врал бы
    при любой смене порта или папки данных.
    """
    from ..core import singleton
    from ..core.config import DATA_DIR

    return {
        "version": "0.1.0",
        "api_url": f"http://{settings.api_host}:{settings.api_port}",
        "data_dir": str(DATA_DIR),
        "artifacts_dir": settings.artifacts_path,
        "auth_file": str(DATA_DIR / "auth.json"),
        # Расписание ведёт ровно один процесс (I-3) — видно, какой именно
        "scheduler_pid": singleton.holder_pid(),
        "daily_budget_usd": settings.daily_llm_budget_usd,
        "max_reply_tokens": settings.max_reply_tokens,
    }


@router.get("/status")
def status(_=Depends(auth)):
    spend = budget.status()
    spend["history"] = budget.history()
    return {
        "spend": spend,
        "integrations": _integrations(),
        "dream": _dream(),
        "runtime": _runtime(),
        # Автопилот выключен по умолчанию и это должно быть видно, а не
        # угадываться: включённый Jarvis тратит деньги сам (R-2)
        "autopilot": _autopilot_state(),
    }


def _autopilot_state() -> dict:
    from ..agents import autopilot as autopilot_mod
    from ..services import runtime_settings

    return {
        "enabled": autopilot_mod.is_enabled(),
        "source": "кнопка" if runtime_settings.autopilot_override() is not None else ".env",
        "interval_min": settings.jarvis_interval_min,
        "max_runs_per_day": settings.jarvis_max_runs_per_day,
        "quiet_hours": [settings.quiet_hours_start, settings.quiet_hours_end],
        "blocked_by": _blocked_reason(),
    }


def _blocked_reason() -> str | None:
    """Почему прогон не пойдёт прямо сейчас — чтобы это не гадали."""
    from ..agents import autopilot as autopilot_mod

    try:
        return autopilot_mod.why_blocked()
    except Exception:
        return None


class AutopilotToggle(BaseModel):
    enabled: bool


@router.get("/autopilot")
def autopilot_state(_=Depends(auth)):
    return _autopilot_state()


@router.post("/autopilot")
def set_autopilot(req: AutopilotToggle, _=Depends(auth)):
    """Включает или выключает автопилот без правки .env и перезапуска.

    Решение человека сильнее переменной среды: переменная — позиция по
    умолчанию при старте, нажатие кнопки — сегодняшнее решение.
    """
    from ..services import runtime_settings

    runtime_settings.set_autopilot(req.enabled)
    return _autopilot_state()
