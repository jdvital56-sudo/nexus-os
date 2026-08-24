"""Напоминания «пора постить» по назначенным черновикам Content Factory.

Публикацию система не делает — фаундер прямо решил (23.08.2026), что
интеграций с площадками не будет, пока он сам не захочет. В назначенный
час приходит сообщение в Telegram, дальше он публикует руками и отмечает
черновик опубликованным.

Джоба живёт в общем планировщике (agents/dream_cadence.py): у него уже
есть межпроцессный замок, второй планировщик прислал бы каждое
напоминание дважды.
"""
import logging

from . import content_factory, telegram_notify

logger = logging.getLogger(__name__)


async def tick() -> int:
    """Проходит по созревшим черновикам и напоминает про каждый.

    Отметку о напоминании ставим только после успешной отправки: если
    Telegram лежал, следующий тик обязан попробовать снова, иначе
    напоминание потеряется совсем.
    """
    due = [i for i in content_factory.due_items() if not i.reminded_at]
    if not due:
        return 0

    sent = 0
    for item in due:
        try:
            ok = await telegram_notify.send_publish_reminder(item)
        except Exception:
            logger.exception("Напоминание по черновику «%s» упало", item.id)
            continue
        if ok:
            content_factory.mark_reminded(item.id)
            sent += 1

    if sent:
        logger.info("Content Factory: напомнил про %d черновик(ов)", sent)
    return sent
