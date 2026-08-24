"""Решение фаундера по черновику, пришедшее кнопкой из Telegram.

Логика живёт в бэкенде, а не в hermes/bot.py: бот — это транспорт, он
только отдаёт нажатие сюда и показывает ответ. Так же можно будет принять
то же решение из интерфейса, не дублируя правила.
"""
import logging

from ..core.errors import NotFoundError
from ..models.schemas import ContentStatus
from . import content_factory, telegram_notify

logger = logging.getLogger(__name__)


def parse_callback(data: str | None) -> tuple[str, str] | None:
    """Разбирает callback_data кнопки. Чужая кнопка — None."""
    if not data:
        return None
    if data.startswith(telegram_notify.APPROVE_PREFIX):
        return "approve", data[len(telegram_notify.APPROVE_PREFIX):]
    if data.startswith(telegram_notify.REJECT_PREFIX):
        return "reject", data[len(telegram_notify.REJECT_PREFIX):]
    return None


async def apply(action: str, item_id: str) -> str:
    """Применяет решение и возвращает текст ответа фаундеру."""
    try:
        item = content_factory.get_item(item_id)
    except NotFoundError:
        # Черновик удалили из интерфейса, а кнопка осталась в переписке
        return "Этот черновик не найден — видимо, уже удалён."

    if action == "reject":
        content_factory.set_status(item_id, ContentStatus.REJECTED)
        return f"🚫 Отклонено: «{item.caption or item.topic}»."

    # Одобренный черновик с датой возвращается в расписание, а не просто в
    # «одобрено»: иначе он выпадет из напоминаний и о нём никто не вспомнит.
    if item.scheduled_at:
        content_factory.set_status(item_id, ContentStatus.SCHEDULED)
        when = item.scheduled_at
        try:
            from datetime import datetime

            when = datetime.fromisoformat(item.scheduled_at).strftime("%d.%m в %H:%M")
        except ValueError:
            logger.warning("Черновик «%s» стоит на непонятной дате «%s»", item_id, item.scheduled_at)
        return f"✅ Одобрено. Напомню {when}, когда придёт время публиковать."

    content_factory.set_status(item_id, ContentStatus.APPROVED)
    return f"✅ Одобрено: «{item.caption or item.topic}». Даты нет — поставьте её в разделе «Контент»."
