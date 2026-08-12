"""Шина событий Nexus OS — единый конверт для всего, что происходит.

Контракт (§3 спецификации), общий для бэкенда и фронтенда:

    {"v": 1, "type": "...", "ts": "ISO-8601 UTC",
     "source": "hermes|jarvis|dream|system|web", "payload": {...}}

Расширять payload можно, переименовывать поля — нельзя без смены `v`.
Незнакомые типы получатель обязан молча игнорировать.

`emit()` вызывается из синхронного кода (запись в память, в граф) и из
рабочих потоков, поэтому он ничего не ждёт и никогда не бросает исключений:
наблюдаемость не имеет права ломать бизнес-логику (I-6).
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Источники
SOURCE_HERMES = "hermes"
SOURCE_JARVIS = "jarvis"
SOURCE_DREAM = "dream"
SOURCE_SYSTEM = "system"
SOURCE_WEB = "web"

# Типы событий из контракта §3
MEMORY_FACT_ADDED = "memory.fact_added"
GRAPH_NODE_ADDED = "graph.node_added"
GRAPH_EDGE_ADDED = "graph.edge_added"
AGENT_RUN_STARTED = "agent.run_started"
AGENT_RUN_FINISHED = "agent.run_finished"
DREAM_FINDING = "dream.finding"
DREAM_COMPLETED = "dream.completed"
CHAT_MESSAGE = "chat.message"
SYSTEM_BUDGET = "system.budget"

Subscriber = Callable[[dict[str, Any]], Awaitable[None]]

_subscribers: list[Subscriber] = []
_loop: asyncio.AbstractEventLoop | None = None


def subscribe(callback: Subscriber) -> None:
    """Подписать корутину на поток событий."""
    _subscribers.append(callback)


def unsubscribe(callback: Subscriber) -> None:
    if callback in _subscribers:
        _subscribers.remove(callback)


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Запомнить основной цикл — из него будут рассылаться события,
    даже когда emit() зовут из рабочего потока (asyncio.to_thread)."""
    global _loop
    _loop = loop


def reset() -> None:
    """Сброс между тестами."""
    global _loop
    _subscribers.clear()
    _loop = None


def make_envelope(event_type: str, payload: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "v": SCHEMA_VERSION,
        "type": event_type,
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "payload": payload,
    }


def emit(event_type: str, payload: dict[str, Any], source: str = SOURCE_SYSTEM) -> None:
    """Разослать событие. Ничего не ждёт и не бросает — только логирует."""
    if not _subscribers:
        return

    envelope = make_envelope(event_type, payload, source)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = _loop

    if loop is None:
        # Некому доставлять: CLI, тесты, скрипт — это не ошибка
        return

    for subscriber in list(_subscribers):
        try:
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(subscriber(envelope), loop)
            else:
                loop.run_until_complete(subscriber(envelope))
        except Exception:
            logger.debug("Событие %s не доставлено подписчику", event_type, exc_info=True)
