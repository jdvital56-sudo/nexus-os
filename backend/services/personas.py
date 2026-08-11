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
