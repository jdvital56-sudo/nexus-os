"""Сторож: проверяет, что система жива, и молчит, пока всё хорошо.

Главное правило — **сторож не ходит в модель**. Ни одной строки к LLM: ни
для проверок, ни для формулировок. Иначе он умрёт от той же поломки, за
которой следит: кончился бюджет — молчит, отвалился ключ — молчит, а именно
в этот момент он и нужен. Здесь только чтение файлов, переменных и часов.

Второе правило — сообщать на **смену состояния**, а не по расписанию.
Сломалось — одно сообщение. Продолжает быть сломанным — тишина. Починилось —
«починилось». Иначе через неделю человек перестанет читать уведомления и
пропустит настоящую поломку.
"""
import logging
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..core.config import DATA_DIR, ensure_data_dir, settings
from ..core.jsonio import read_json, write_json

logger = logging.getLogger(__name__)

STATE_FILE = DATA_DIR / "watchdog_state.json"

# Сколько гигабайт на диске считаем тревогой: ниже этого установка любого
# пакета или рост базы ломает систему целиком
MIN_FREE_GB = 5

# Ночной прогон раз в сутки; двое суток тишины — это уже поломка
DREAM_SILENCE_HOURS = 48


@dataclass
class Check:
    id: str
    label: str
    ok: bool
    detail: str
    critical: bool = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _check_data_dir() -> Check:
    try:
        ensure_data_dir()
        probe = Path(DATA_DIR) / ".watchdog_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return Check("data_dir", "Папка данных", True, str(DATA_DIR), critical=True)
    except Exception as e:
        return Check("data_dir", "Папка данных", False, f"не пишется: {e}", critical=True)


def _check_disk() -> Check:
    try:
        free_gb = shutil.disk_usage(str(DATA_DIR)).free / 1024**3
    except Exception as e:
        return Check("disk", "Место на диске", False, str(e))
    ok = free_gb >= MIN_FREE_GB
    return Check(
        "disk",
        "Место на диске",
        ok,
        f"свободно {free_gb:.1f} ГБ" + ("" if ok else f", меньше порога {MIN_FREE_GB} ГБ"),
        critical=True,
    )


def _check_llm_key() -> Check:
    """Хотя бы один способ говорить с моделью должен быть настроен."""
    keys = {
        "deepseek": settings.deepseek_api_key,
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "ollama": settings.llm_provider == "ollama",
    }
    live = [name for name, value in keys.items() if value]
    return Check(
        "llm",
        "Доступ к моделям",
        bool(live),
        ", ".join(live) if live else "не задан ни один ключ — система онемеет",
        critical=True,
    )


def _check_telegram() -> Check:
    ok = bool(settings.telegram_bot_token and settings.telegram_allowed_user_id)
    return Check(
        "telegram",
        "Телеграм",
        ok,
        "бот и получатель заданы" if ok else "нет токена бота или id получателя",
    )


def _check_memory() -> Check:
    try:
        from . import memory as memory_svc

        facts = memory_svc.get_facts(limit=1)
        return Check("memory", "Память", True, f"читается, фактов в выдаче: {len(facts)}", critical=True)
    except Exception as e:
        return Check("memory", "Память", False, f"не читается: {e}", critical=True)


def _check_graph() -> Check:
    try:
        from . import graph as graph_svc

        stats = graph_svc.get_stats()
        # Пустой граф — не поломка: он наполняется разговорами
        return Check("graph", "Граф знаний", True, f"{stats.nodes} узлов, {stats.edges} связей")
    except Exception as e:
        return Check("graph", "Граф знаний", False, f"не читается: {e}")


def _check_budget() -> Check:
    try:
        from . import budget

        state = budget.status()
    except Exception as e:
        return Check("budget", "Бюджет", False, f"не считается: {e}")
    return Check(
        "budget",
        "Бюджет",
        not state["throttled"],
        f"потрачено ${state['spent_usd']} из ${state['budget_usd']}"
        + (" — фон остановлен" if state["throttled"] else ""),
    )


def _check_scheduler() -> Check:
    """Расписание должен вести ровно один живой процесс."""
    from ..core import singleton

    pid = singleton.holder_pid()
    if not pid:
        return Check("scheduler", "Расписание", False, "никто не ведёт: ночной прогон не запустится", critical=True)
    alive = singleton._alive(pid)
    return Check(
        "scheduler",
        "Расписание",
        alive,
        f"ведёт процесс {pid}" if alive else f"процесс {pid} мёртв, замок завис",
        critical=True,
    )


def _check_dream() -> Check:
    try:
        from . import dream

        brief = dream.get_brief()
    except Exception as e:
        return Check("dream", "Ночной прогон", False, f"не читается: {e}")

    if not brief:
        return Check("dream", "Ночной прогон", True, "ещё ни разу не запускался")

    created = str(brief.get("created_at", ""))
    try:
        when = datetime.fromisoformat(created)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
    except ValueError:
        return Check("dream", "Ночной прогон", True, "время последнего прогона неизвестно")

    hours = (_now() - when).total_seconds() / 3600
    ok = hours <= DREAM_SILENCE_HOURS
    return Check(
        "dream",
        "Ночной прогон",
        ok,
        f"последний {hours:.0f} ч назад" + ("" if ok else " — молчит дольше двух суток"),
    )


def _check_obsidian() -> Check:
    path = settings.obsidian_vault_path
    if not path:
        return Check("obsidian", "База знаний", True, "не подключена — это допустимо")
    exists = Path(path).exists()
    return Check(
        "obsidian",
        "База знаний",
        exists,
        path if exists else f"папка пропала: {path}",
    )


CHECKS = (
    _check_data_dir,
    _check_disk,
    _check_llm_key,
    _check_memory,
    _check_graph,
    _check_scheduler,
    _check_dream,
    _check_budget,
    _check_telegram,
    _check_obsidian,
)

# Проверки, которые сторож умеет не только находить, но и чинить сам —
# и функция, которой это делать. Пока одна: мёртвый замок расписания.
_HEALERS = {}


def _heal_scheduler() -> Check | None:
    """Перехватывает расписание, если его держит мёртвый процесс (или никто).

    Safe to call always: `dream_cadence.start()` сам ничего не делает, если
    расписание в этом процессе уже идёт (см. core/singleton.py — acquire()
    и так забирает замок у мёртвого pid, тут просто дёргаем это заново,
    не дожидаясь перезапуска бэкенда).
    """
    try:
        from ..agents.dream_cadence import dream_cadence

        dream_cadence.start()
    except Exception:
        logger.exception("Сторож не смог перехватить расписание")
        return None
    return _check_scheduler()


_HEALERS["scheduler"] = _heal_scheduler


def run(heal: bool = False) -> dict:
    """Прогоняет все проверки. Ни одного обращения к модели.

    `heal=True` — вдобавок пытается починить то, что умеет (сейчас только
    мёртвый замок расписания), и перепроверяет результат. По умолчанию
    выключено: `heal` трогает настоящий APScheduler, а не только файлы, —
    в тестах и в фоновой джобе сторожа (там своя причина, см. check_and_notify)
    он не нужен.
    """
    checks = []
    for check in CHECKS:
        try:
            result = check()
        except Exception as e:
            # Сама проверка не имеет права уронить сторожа
            logger.exception("Проверка %s упала", check.__name__)
            result = Check(check.__name__, check.__name__, False, f"проверка сломалась: {e}")

        if heal and not result.ok:
            healer = _HEALERS.get(result.id)
            if healer:
                healed = healer()
                if healed is not None:
                    result = healed

        checks.append(result)

    broken = [c for c in checks if not c.ok]
    critical = [c for c in broken if c.critical]
    return {
        "checked_at": _now().isoformat(),
        "healthy": not broken,
        "critical_count": len(critical),
        "broken_count": len(broken),
        "checks": [asdict(c) for c in checks],
    }


def _load_state() -> dict:
    ensure_data_dir()
    return read_json(STATE_FILE, {}) or {}


def changes_since_last_run(report: dict) -> tuple[list[dict], list[dict]]:
    """Что сломалось и что починилось с прошлой проверки.

    Возвращает две пачки: новые поломки и новые починки. Всё, что не
    изменилось, сюда не попадает — на этом и держится молчание сторожа.
    """
    previous = _load_state().get("checks", {})
    broke, fixed = [], []
    for check in report["checks"]:
        was_ok = previous.get(check["id"])
        if was_ok is None:
            # Первый прогон: сообщаем только о поломках, не о том, что всё цело
            if not check["ok"]:
                broke.append(check)
            continue
        if was_ok and not check["ok"]:
            broke.append(check)
        elif not was_ok and check["ok"]:
            fixed.append(check)
    return broke, fixed


def remember(report: dict) -> None:
    ensure_data_dir()
    write_json(
        STATE_FILE,
        {
            "checked_at": report["checked_at"],
            "checks": {c["id"]: c["ok"] for c in report["checks"]},
        },
    )


def format_message(broke: list[dict], fixed: list[dict]) -> str:
    """Текст для Телеграма. Пишется руками, а не моделью — по тем же причинам."""
    lines = []
    if broke:
        lines.append("Сломалось:")
        for c in broke:
            mark = "!" if c.get("critical") else "-"
            lines.append(f"{mark} {c['label']}: {c['detail']}")
    if fixed:
        if lines:
            lines.append("")
        lines.append("Починилось:")
        for c in fixed:
            lines.append(f"+ {c['label']}: {c['detail']}")
    return "\n".join(lines)


async def check_and_notify(send=None) -> dict:
    """Проверить, сообщить об изменениях, запомнить состояние.

    `send` — как отправлять сообщение. По умолчанию Телеграм; в тестах
    подменяется, чтобы ничего никуда не улетало.
    """
    report = run()
    broke, fixed = changes_since_last_run(report)

    if broke or fixed:
        text = format_message(broke, fixed)
        try:
            if send is None:
                from ..agents.dream_cadence import dream_cadence

                await dream_cadence.send_brief_to_telegram(text)
            else:
                await send(text)
        except Exception:
            logger.exception("Сторож не смог отправить сообщение")
    else:
        logger.debug("Сторож: без изменений")

    remember(report)
    report["notified"] = bool(broke or fixed)
    return report
