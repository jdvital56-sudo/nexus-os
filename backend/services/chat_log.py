"""Полная лента переписки — то, что человек читает на экране.

Отдельно от `dialog_history` намеренно. Тот буфер существует ради промпта:
двенадцать последних реплик, каждая обрезана до 600 символов, чтобы не
раздувать запрос к модели. Экран же читал именно его — и длинные ответы
обрывались на полуслове, а после перезагрузки страницы обрывались навсегда.

Здесь текст хранится целиком и глубже: это архив разговора, а не контекст.
"""
import logging
import threading
from datetime import datetime
from typing import Any

from ..core.config import DATA_DIR, ensure_data_dir
from ..core.jsonio import read_json, write_json

logger = logging.getLogger(__name__)

LOG_FILE = DATA_DIR / "chat_log.json"

# Сколько реплик держим на канал. Дальше — уже не переписка, а архив,
# и искать в нём надо памятью, а не листанием
MAX_MESSAGES = 400

# Потолок на реплику: защита от простыни на мегабайт, а не экономия
MAX_CHARS = 20000

_lock = threading.Lock()


def _key(channel: str, user_id: str) -> str:
    return f"{channel}:{user_id}"


def _load() -> dict[str, list[dict]]:
    ensure_data_dir()
    data = read_json(LOG_FILE, {})
    return data if isinstance(data, dict) else {}


def append(channel: str, user_id: str, role: str, text: str, persona: str = "") -> None:
    append_turn(channel, user_id, [(role, text, persona)])


def append_turn(channel: str, user_id: str, items: list[tuple[str, str, str]]) -> None:
    key = _key(channel, user_id)
    now = datetime.utcnow().isoformat()
    with _lock:
        data = _load()
        messages: list[dict[str, Any]] = data.get(key, [])
        for role, text, persona in items:
            messages.append(
                {
                    "role": role,
                    "text": (text or "")[:MAX_CHARS],
                    "persona": persona,
                    "at": now,
                }
            )
        data[key] = messages[-MAX_MESSAGES:]
        ensure_data_dir()
        write_json(LOG_FILE, data)


def recent(channel: str, user_id: str, limit: int = 100) -> list[dict]:
    with _lock:
        messages = _load().get(_key(channel, user_id), [])
    return messages[-limit:] if limit > 0 else messages


def clear(channel: str, user_id: str) -> int:
    with _lock:
        data = _load()
        removed = len(data.pop(_key(channel, user_id), []))
        if removed:
            ensure_data_dir()
            write_json(LOG_FILE, data)
    return removed
