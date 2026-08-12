"""Хранилище Пантеона: персоны и системный промпт Hermes.

До этого персоны жили только в памяти процесса — правка не переживала
рестарт и не была видна другим каналам. Здесь они лежат в JSON рядом с
остальными данными и читаются на каждое сообщение, поэтому изменение
через API влияет уже на следующий ответ.
"""
import logging
from typing import Any

from ..core.config import DATA_DIR, ensure_data_dir
from ..core.errors import NotFoundError
from ..core.jsonio import read_json, write_json

logger = logging.getLogger(__name__)

PERSONAS_FILE = DATA_DIR / "personas.json"

# Промпт поверх персоны: общие правила поведения Hermes, которые фаундер
# правит из Mission Control, не трогая каждую персону по отдельности.
DEFAULT_SYSTEM_PROMPT = (
    "Ты — Hermes, голос Nexus OS. Отвечай по делу и кратко. "
    "Не выдумывай факты: если чего-то не знаешь, скажи прямо. "
    "Необратимые действия только предлагай — решение принимает человек.\n"
    "Пиши обычным текстом без markdown-разметки: без звёздочек для жирного, "
    "без решёток для заголовков, без markdown-таблиц. Списки — обычным дефисом. "
    "Ответ читают в мессенджере, где разметка видна как мусор."
)

REQUIRED_FIELDS = ("name", "description", "model", "provider", "system_prompt")

# Характер Hermes: не отдельная персона, а настройка поверх любой из них.
# Ползунок 0..10 понятнее фаундеру, чем правка промпта руками, а на модель
# всё равно уходит текстом — иначе она его не поймёт.
DEFAULT_CHARACTER = {
    "humor": 3,        # сухо ← → с шутками
    "warmth": 5,       # по-деловому ← → по-дружески
    "verbosity": 4,    # односложно ← → подробно
    "address": "ты",   # ты | вы | сэр
    "language": "auto",  # auto | ru | en
}

_ADDRESS = {
    "ты": "Обращайся ко мне на «ты».",
    "вы": "Обращайся ко мне на «вы».",
    "сэр": "Обращайся ко мне на «вы» и называй «сэр» — но не в каждой фразе, а к месту.",
}

_LANGUAGE = {
    "auto": "Отвечай на том языке, на котором к тебе обратились.",
    "ru": "Всегда отвечай по-русски, даже если вопрос задан на другом языке.",
    "en": "Always answer in English, even if the question is asked in another language.",
}


def _level(value: Any, default: int) -> int:
    try:
        return max(0, min(10, int(value)))
    except (TypeError, ValueError):
        return default


def describe_character(character: dict[str, Any] | None = None) -> str:
    """Превращает ползунки в понятные модели указания.

    Числа модели ничего не говорят: «юмор 7» она трактует как угодно.
    Поэтому каждый уровень разворачивается во фразу.
    """
    c = {**DEFAULT_CHARACTER, **(character or {})}
    parts = []

    humor = _level(c.get("humor"), DEFAULT_CHARACTER["humor"])
    if humor <= 2:
        parts.append("Не шути и не балагурь — только по делу.")
    elif humor <= 6:
        parts.append("Лёгкая ирония уместна, но не в ущерб сути.")
    else:
        parts.append("Шути охотно и живо, если это не мешает ответу.")

    warmth = _level(c.get("warmth"), DEFAULT_CHARACTER["warmth"])
    if warmth <= 2:
        parts.append("Тон сдержанный и деловой, без личного участия.")
    elif warmth <= 6:
        parts.append("Тон спокойный и человечный, без панибратства.")
    else:
        parts.append("Тон тёплый и дружеский, как у давнего напарника.")

    verbosity = _level(c.get("verbosity"), DEFAULT_CHARACTER["verbosity"])
    if verbosity <= 2:
        parts.append("Отвечай очень коротко — одно-два предложения.")
    elif verbosity <= 6:
        parts.append("Отвечай сжато, без вводных и повторов.")
    else:
        parts.append("Разворачивай ответ: объясняй причины и предлагай следующий шаг.")

    parts.append(_ADDRESS.get(str(c.get("address")), _ADDRESS["ты"]))
    parts.append(_LANGUAGE.get(str(c.get("language")), _LANGUAGE["auto"]))
    return " ".join(parts)


def get_character() -> dict[str, Any]:
    stored = _load().get("character") or {}
    return {**DEFAULT_CHARACTER, **stored}


def set_character(payload: dict[str, Any]) -> dict[str, Any]:
    """Сохраняет характер. Правка влияет уже на следующее сообщение."""
    current = get_character()
    for dial in ("humor", "warmth", "verbosity"):
        if payload.get(dial) is not None:
            current[dial] = _level(payload[dial], DEFAULT_CHARACTER[dial])
    if payload.get("address") in _ADDRESS:
        current["address"] = payload["address"]
    if payload.get("language") in _LANGUAGE:
        current["language"] = payload["language"]

    data = _load()
    data["character"] = current
    _save(data)
    logger.info("Характер Hermes обновлён: %s", current)
    return current


def _defaults() -> list[dict]:
    # Импорт внутри функции — PersonaManager сам зависит от этого модуля
    from ..agents.persona_manager import PersonaManager

    return [dict(p) for p in PersonaManager.DEFAULT_PERSONAS]


def _load() -> dict[str, Any]:
    ensure_data_dir()
    data = read_json(PERSONAS_FILE)
    if not isinstance(data, dict) or "personas" not in data:
        data = {"personas": _defaults(), "system_prompt": DEFAULT_SYSTEM_PROMPT}
        write_json(PERSONAS_FILE, data)
    return data


def _save(data: dict[str, Any]) -> None:
    ensure_data_dir()
    write_json(PERSONAS_FILE, data)


def list_personas() -> list[dict]:
    return _load()["personas"]


def get_persona(name: str) -> dict | None:
    for persona in list_personas():
        if persona["name"].lower() == name.lower():
            return persona
    return None


def create_persona(payload: dict) -> dict:
    missing = [f for f in REQUIRED_FIELDS if not payload.get(f)]
    if missing:
        raise ValueError(f"Не заполнены поля: {', '.join(missing)}")

    data = _load()
    if any(p["name"].lower() == payload["name"].lower() for p in data["personas"]):
        raise ValueError(f"Персона '{payload['name']}' уже существует")

    persona = {f: payload[f] for f in REQUIRED_FIELDS}
    data["personas"].append(persona)
    _save(data)
    logger.info("Добавлена персона %s (%s/%s)", persona["name"], persona["provider"], persona["model"])
    return persona


def update_persona(name: str, payload: dict) -> dict:
    data = _load()
    for persona in data["personas"]:
        if persona["name"].lower() != name.lower():
            continue
        for field in ("description", "model", "provider", "system_prompt"):
            if payload.get(field) is not None:
                persona[field] = payload[field]
        _save(data)
        logger.info("Персона %s обновлена -> %s/%s", persona["name"], persona["provider"], persona["model"])
        return persona
    raise NotFoundError("Persona", name)


def delete_persona(name: str) -> bool:
    data = _load()
    remaining = [p for p in data["personas"] if p["name"].lower() != name.lower()]
    if len(remaining) == len(data["personas"]):
        raise NotFoundError("Persona", name)
    if not remaining:
        raise ValueError("Нельзя удалить последнюю персону")
    data["personas"] = remaining
    _save(data)
    return True


def get_system_prompt() -> str:
    return _load().get("system_prompt", DEFAULT_SYSTEM_PROMPT)


def set_system_prompt(prompt: str) -> str:
    if not prompt or not prompt.strip():
        raise ValueError("Системный промпт не может быть пустым")
    data = _load()
    data["system_prompt"] = prompt.strip()
    _save(data)
    logger.info("Системный промпт Hermes обновлён (%d символов)", len(data["system_prompt"]))
    return data["system_prompt"]


def reset_to_defaults() -> dict[str, Any]:
    """Возврат к заводскому Пантеону — на случай, если правки завели в тупик."""
    data = {"personas": _defaults(), "system_prompt": DEFAULT_SYSTEM_PROMPT}
    _save(data)
    return data
