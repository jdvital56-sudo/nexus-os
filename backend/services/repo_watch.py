# -*- coding: utf-8 -*-
"""Сторож репозиториев: напоминает про работу, которая не уехала в git.

07.09.2026. Повод — реальная потеря: фаундер был уверен, что репозиторий
обновляется сам («мы договаривались автоматически»), а автоотправки кода не
существовало никогда. За 11 дней в рабочем каталоге накопилось незакоммичено
всё подряд, включая починку TLS, без которой не работал ни один HTTPS-вызов
из Python. Нашлось это только потому, что он спросил вслух.

**Почему напоминание, а не автокоммит.** Коммитить по таймеру нельзя: в
этом же каталоге одновременно работают несколько сессий, для того и стоит
заслон от `git add -A` (см. `.githooks/pre-commit`). Таймер поймал бы
недописанный код посреди правки и утащил чужие файлы — ровно то, от чего
заслон и защищает. Поэтому здесь только глаза: система замечает и говорит,
решение коммитить остаётся за человеком.

Модель не трогается: только `git status` и `git log`. Работает и когда
кончился бюджет, и когда отвалился ключ, — как сторож `watchdog.py`.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Сколько часов работа может лежать незакоммиченной, прежде чем это станет
# поводом написать. Меньше суток — это обычная работа в процессе, про неё
# напоминать значит приучить человека не читать сообщения.
STALE_HOURS = int(os.getenv("NEXUS_REPO_STALE_HOURS", "24"))

# Сколько секунд ждём git. Локальные команды мгновенные; таймаут здесь на
# случай залипшего индекса или сетевого диска, чтобы сторож не завис молча.
GIT_TIMEOUT = 20


def watched_repos() -> list[Path]:
    """Какие репозитории сторожим.

    По умолчанию — сам Nexus OS. Остальные добавляются переменной
    `NEXUS_WATCHED_REPOS` через `;` — у фаундера рядом лежат Holovant и
    хранилище Obsidian, и терять работу там ровно так же неприятно.
    """
    raw = os.getenv("NEXUS_WATCHED_REPOS", "").strip()
    if raw:
        paths = [Path(p.strip()) for p in raw.split(";") if p.strip()]
    else:
        paths = [Path(__file__).resolve().parents[2]]
    return [p for p in paths if (p / ".git").exists()]


def _git(repo: Path, *args: str) -> str:
    """Запускает git и возвращает вывод. Ошибка — пустая строка.

    `core.quotepath=false` обязателен: без него git экранирует не-ASCII имена
    файлов в вид `\\320\\222...`, и в сообщении фаундеру вместо «Вадим» была
    бы каша. На этой машине кириллица в путях — норма, а не исключение.
    """
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("git %s в %s не отработал: %s", " ".join(args), repo.name, e)
        return ""
    if result.returncode != 0:
        logger.info("git %s в %s: код %d", " ".join(args), repo.name, result.returncode)
        return ""
    return result.stdout


def _oldest_change_hours(repo: Path, files: list[str]) -> float:
    """Возраст самой давней незакоммиченной правки, в часах.

    Смотрим время изменения файла, а не время последнего коммита: важно
    именно «сколько эта работа лежит», а не когда в репозиторий последний
    раз что-то приносили.
    """
    now = time.time()
    ages = []
    for name in files:
        path = repo / name
        try:
            ages.append((now - path.stat().st_mtime) / 3600)
        except OSError:
            # Файл удалён или переименован — его возраст не измерить, и это
            # не повод ронять весь обход
            continue
    return max(ages) if ages else 0.0


def status(repo: Path) -> dict:
    """Что в репозитории не уехало: незакоммиченное и неотправленное."""
    dirty_raw = _git(repo, "status", "--porcelain")
    # Первые три символа — коды состояния, дальше путь
    files = [line[3:] for line in dirty_raw.splitlines() if len(line) > 3]

    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    unpushed_raw = _git(repo, "log", "--oneline", "@{upstream}..HEAD") if branch else ""
    unpushed = [ln for ln in unpushed_raw.splitlines() if ln.strip()]

    return {
        "name": repo.name,
        "path": str(repo),
        "branch": branch,
        "dirty_count": len(files),
        "dirty_files": files,
        "oldest_hours": round(_oldest_change_hours(repo, files), 1),
        "unpushed_count": len(unpushed),
    }


def _describe(state: dict) -> str | None:
    """Строка про один репозиторий. None — сообщать не о чем.

    Молчим о свежей работе: правка, сделанная час назад, — это человек за
    работой, а не потеря. Неотправленные коммиты сообщаем всегда: они уже
    закончены, и держать их на одной машине незачем.
    """
    stale = state["dirty_count"] and state["oldest_hours"] >= STALE_HOURS
    if not stale and not state["unpushed_count"]:
        return None

    parts = []
    if stale:
        days = state["oldest_hours"] / 24
        age = f"{days:.0f} дн." if days >= 1 else f"{state['oldest_hours']:.0f} ч."
        parts.append(f"незакоммичено файлов: {state['dirty_count']}, самому старому {age}")
    if state["unpushed_count"]:
        parts.append(f"не отправлено коммитов: {state['unpushed_count']}")

    line = f"📦 {state['name']} ({state['branch']}) — " + "; ".join(parts)
    if stale:
        # Имена файлов важнее счётчика: по ним сразу видно, своя это работа
        # или соседней сессии, и стоит ли вообще трогать
        shown = state["dirty_files"][:5]
        line += "\n   " + ", ".join(shown)
        if state["dirty_count"] > len(shown):
            line += f" и ещё {state['dirty_count'] - len(shown)}"
    return line


def digest_text() -> str:
    """Текст напоминания. Пустая строка — всё уехало, писать не о чем."""
    lines = [d for repo in watched_repos() if (d := _describe(status(repo)))]
    if not lines:
        return ""
    return (
        "Работа, которая ещё не уехала в git:\n\n"
        + "\n\n".join(lines)
        + "\n\nАвтокоммита нет намеренно: в каталоге работают несколько сессий, "
        "и таймер утащил бы чужое."
    )


async def tick() -> int:
    """Задание планировщика. Возвращает число репозиториев в сообщении."""
    import asyncio

    # git — блокирующий вызов; без to_thread он останавливал бы весь
    # событийный цикл бэкенда, включая голос, на время обхода
    text = await asyncio.to_thread(digest_text)
    if not text:
        logger.info("Сторож репозиториев: всё уехало")
        return 0

    from . import telegram_notify

    await telegram_notify.send_message(text)
    count = text.count("📦")
    logger.info("Сторож репозиториев: сообщил о %d репозитории(ях)", count)
    return count
