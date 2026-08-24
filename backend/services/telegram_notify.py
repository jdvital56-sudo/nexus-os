"""Отправка сообщений фаундеру в Telegram из бэкенда.

Бот Hermes (hermes/bot.py) живёт отдельным процессом и слушает входящие.
Бэкенду нужно уметь писать первым — напомнить «пора постить», прислать
черновик на подтверждение. Тащить ради этого python-telegram-bot в процесс
API незачем: один POST на Bot API делает ровно то же самое.

Молчим, а не падаем: если токен или адресат не настроены, вызывающий код
должен продолжать работать (см. content_factory.send_for_approval —
черновик остаётся DRAFT, а не зависает в «ждёт подтверждения» навсегда).
"""
import logging

import httpx

from ..core.config import settings
from ..models.schemas import ContentItem

logger = logging.getLogger(__name__)

API_ROOT = "https://api.telegram.org"
TIMEOUT_SECONDS = 15.0

# Префикс callback_data кнопок. Telegram ограничивает callback_data 64
# байтами, id черновика — 8 символов, влезаем с запасом.
APPROVE_PREFIX = "content:approve:"
REJECT_PREFIX = "content:reject:"


def _config() -> tuple[str, str] | None:
    token = settings.telegram_bot_token
    chat_id = settings.telegram_allowed_user_id
    if not token or not chat_id:
        logger.info("Telegram не настроен (нет токена или id получателя) — сообщение не отправлено")
        return None
    return token, chat_id


async def _post(method: str, payload: dict) -> bool:
    conf = _config()
    if conf is None:
        return False
    token, chat_id = conf

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{API_ROOT}/bot{token}/{method}",
                json={"chat_id": chat_id, **payload},
            )
            resp.raise_for_status()
    except Exception as e:
        # Телеграм лежит или токен протух — это не повод валить весь
        # конвейер контента, черновик уже создан и никуда не денется.
        logger.warning("Не удалось отправить в Telegram (%s): %s", method, e)
        return False
    return True


async def send_message(text: str) -> bool:
    """Простое текстовое сообщение фаундеру."""
    return await _post("sendMessage", {"text": text})


def _draft_summary(item: ContentItem) -> str:
    lines = [f"📝 Черновик «{item.topic}»"]
    if item.caption:
        lines.append(f"Подпись: {item.caption}")
    if item.script:
        lines.append(f"Сценарий: {item.script}")
    if item.hashtags:
        lines.append(" ".join(f"#{h.lstrip('#')}" for h in item.hashtags))
    if item.platforms:
        lines.append(f"Площадки: {', '.join(item.platforms)}")
    if item.scheduled_at:
        lines.append(f"Запланировано: {item.scheduled_at}")

    ready = [
        name
        for name, value in (("голос", item.voice_file), ("картинка", item.image_file), ("видео", item.video_file))
        if value
    ]
    lines.append("Готово: " + (", ".join(ready) if ready else "только текст"))
    return "\n".join(lines)


async def send_approval_request(item: ContentItem) -> bool:
    """Шлёт черновик с кнопками «Одобрить»/«Отклонить».

    Кнопки, а не текстовая команда с id: фаундер прямо просил «проверю и
    дам добро» — печатать восьмисимвольный идентификатор с телефона он не
    станет.
    """
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Одобрить", "callback_data": f"{APPROVE_PREFIX}{item.id}"},
            {"text": "🚫 Отклонить", "callback_data": f"{REJECT_PREFIX}{item.id}"},
        ]]
    }
    return await _post(
        "sendMessage",
        {"text": _draft_summary(item), "reply_markup": keyboard},
    )


async def send_publish_reminder(item: ContentItem) -> bool:
    """Напоминание в назначенный час: система сама никуда не публикует."""
    platforms = ", ".join(item.platforms) if item.platforms else "площадки не заданы"
    text = (
        f"⏰ Пора публиковать: «{item.caption or item.topic}»\n"
        f"Площадки: {platforms}\n"
        f"Файлы лежат в разделе «Контент» — публикуете вручную."
    )
    return await _post("sendMessage", {"text": text})
