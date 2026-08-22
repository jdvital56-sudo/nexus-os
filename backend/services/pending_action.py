"""Заблокированное действие ждёт явного «подтверждаю» — второй шаг защиты
computer_use.py, план 19.08.2026, следующий по плану раунд.

Хранилище в памяти процесса, не на диске: подтверждение имеет смысл только
пока экран не изменился с момента отказа, переживать перезапуск бэкенда ему
незачем. Ключ — «channel:user_id», тот же принцип разделения, что у
dialog_history: если завтра появится второй канал/пользователь, заблокированный
клик из одного разговора не подтвердится случайно из другого.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Сколько ждём «подтверждаю», прежде чем действие протухнет. Не бесконечно:
# за это время экран мог измениться (страница ушла, всплыло окно), и старые
# координаты стали бы промахом мимо цели, а не той кнопкой, что видел фаундер.
TTL_SECONDS = 180


@dataclass
class PendingAction:
    kind: str  # "click" | "type"
    payload: dict[str, Any]
    description: str
    # Лямбда, а не time.monotonic напрямую: default_factory=time.monotonic
    # захватил бы саму функцию один раз при импорте модуля — тесты,
    # подменяющие pending_action.time.monotonic (см. test_pending_action.py),
    # эту уже захваченную ссылку не увидят. Лямбда ищет атрибут заново при
    # каждом создании записи.
    created_at: float = field(default_factory=lambda: time.monotonic())


_store: dict[str, PendingAction] = {}


def hold(key: str, kind: str, payload: dict[str, Any], description: str) -> None:
    """Запоминает отказанное действие. Новый вызов молча заменяет старый —
    последний заблокированный клик и есть тот, о котором спрашивают."""
    _store[key] = PendingAction(kind=kind, payload=payload, description=description)


def get(key: str) -> PendingAction | None:
    """Возвращает ожидающее действие, если оно есть и не протухло."""
    action = _store.get(key)
    if action is None:
        return None
    if time.monotonic() - action.created_at > TTL_SECONDS:
        logger.info("Заблокированное действие протухло без подтверждения: %s", action.description)
        del _store[key]
        return None
    return action


def clear(key: str) -> None:
    _store.pop(key, None)
