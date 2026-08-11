"""Короткая память диалога — последние реплики канала.

Долгая память (`memory.recall`) ищет по смыслу и возвращает то, что похоже
на текущий вопрос. Этого не хватает для нити разговора: на «переделай, но
короче» или «а что я только что сказал» похожих фактов не находится, и
модель отвечала вслепую — каждое сообщение уходило к ней в одиночку.

Здесь лежит буфер последних реплик на пару «канал + пользователь». Он
маленький намеренно: длинный контекст размывает ответ и стоит денег, а всё,
что важно надолго, и так оседает в памяти фактов (I-2).

Файл переживает перезапуск бота — иначе нить рвалась бы на каждом деплое.
"""
import logging
import threading
from datetime import datetime, timedelta
from typing import Any

from ..core.config import DATA_DIR, ensure_data_dir
from ..core.jsonio import read_json, write_json

logger = logging.getLogger(__name__)

HISTORY_FILE = DATA_DIR / "dialog_history.json"

# Сколько реплик держим (не пар): шесть обменов — нить видна, промпт не пухнет
MAX_TURNS = 12

# Длинные реплики режем: в контексте важен ход разговора, а не каждое слово
MAX_CHARS = 600

# Пауза, после которой разговор считается новым. Вчерашняя переписка,
# подмешанная в сегодняшний вопрос, сбивает модель сильнее, чем помогает.
SESSION_GAP_HOURS = 6

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

# Файл читают и пишут фоновые потоки (asyncio.to_thread) — без замка две
# параллельные записи затирали бы друг друга целиком
_lock = threading.Lock()


def _key(channel: str, user_id: str) -> str:
    return f"{channel}:{user_id}"


def _load() -> dict[str, list[dict]]:
    ensure_data_dir()
    data = read_json(HISTORY_FILE, {})
    return data if isinstance(data, dict) else {}


def _save(data: dict[str, list[dict]]) -> None:
    ensure_data_dir()
    write_json(HISTORY_FILE, data)


def _entry(role: str, text: str, persona: str) -> dict[str, Any]:
    clipped = (text or "").strip()
    if len(clipped) > MAX_CHARS:
        clipped = clipped[:MAX_CHARS].rstrip() + "…"
    return {
        "role": role,
        "text": clipped,
        "persona": persona,
        "at": datetime.utcnow().isoformat(),
    }


def append(channel: str, user_id: str, role: str, text: str, persona: str = "") -> None:
    """Дописывает одну реплику, обрезая буфер до последних MAX_TURNS."""
    append_many(channel, user_id, [(role, text, persona)])


def append_turn(
    channel: str, user_id: str, user_text: str, reply: str, persona: str = ""
) -> None:
    """Пара «вопрос-ответ» одной записью на диск — вдвое меньше обращений."""
    append_many(
        channel,
        user_id,
        [(ROLE_USER, user_text, ""), (ROLE_ASSISTANT, reply, persona)],
    )


def append_many(
    channel: str, user_id: str, items: list[tuple[str, str, str]]
) -> None:
    key = _key(channel, user_id)
    with _lock:
        data = _load()
        turns = data.get(key, [])
        turns.extend(_entry(role, text, persona) for role, text, persona in items)
        data[key] = turns[-MAX_TURNS:]
        _save(data)


def recent(channel: str, user_id: str, limit: int = MAX_TURNS) -> list[dict]:
    """Последние реплики. После долгой паузы — пусто: это уже другой разговор."""
    with _lock:
        turns = _load().get(_key(channel, user_id), [])

    if not turns:
        return []

    if _is_stale(turns[-1]):
        return []

    return turns[-limit:] if limit > 0 else []


def _is_stale(entry: dict) -> bool:
    """Разрыв сессии. Битую дату считаем свежей — лучше лишний контекст, чем потеря нити."""
    try:
        last = datetime.fromisoformat(entry["at"])
    except (KeyError, TypeError, ValueError):
        return False
    return datetime.utcnow() - last > timedelta(hours=SESSION_GAP_HOURS)


def render(channel: str, user_id: str, limit: int = MAX_TURNS) -> str:
    """Готовый блок для промпта. Пустая история — пустая строка, без шапки."""
    turns = recent(channel, user_id, limit)
    if not turns:
        return ""

    lines = ["Недавняя переписка (свежие реплики внизу):"]
    for turn in turns:
        if turn.get("role") == ROLE_USER:
            speaker = "Пользователь"
        else:
            speaker = turn.get("persona") or "Ассистент"
        lines.append(f"{speaker}: {turn.get('text', '')}")
    return "\n".join(lines)


def clear(channel: str, user_id: str) -> int:
    """Забыть нить разговора. Возвращает, сколько реплик выброшено."""
    key = _key(channel, user_id)
    with _lock:
        data = _load()
        removed = len(data.pop(key, []))
        if removed:
            _save(data)
    return removed
