"""Кнопки «Одобрить»/«Отклонить» в Telegram и текст сообщения с черновиком.

Фаундер просил: «перед тем как отправить, пришли в Telegram, я проверю и
дам добро». Печатать восьмисимвольный id с телефона он не станет — значит
кнопки, а не текстовая команда.
"""
import httpx
import pytest

from backend.models.schemas import ContentItem, ContentStatus
from backend.services import content_approval, telegram_notify


def _item(**kwargs) -> ContentItem:
    base = dict(
        id="abc12345",
        topic="утренние ритуалы",
        script="Сценарий про кофе",
        caption="Подпись",
        hashtags=["кофе"],
        platforms=["instagram"],
    )
    base.update(kwargs)
    return ContentItem(**base)


# === Разбор callback_data кнопки ===

def test_parse_approve():
    action, item_id = content_approval.parse_callback("content:approve:abc12345")
    assert (action, item_id) == ("approve", "abc12345")


def test_parse_reject():
    action, item_id = content_approval.parse_callback("content:reject:abc12345")
    assert (action, item_id) == ("reject", "abc12345")


def test_parse_foreign_callback():
    """Чужая кнопка — не наше дело, молча пропускаем."""
    assert content_approval.parse_callback("wallet:pay:7") is None
    assert content_approval.parse_callback("") is None
    assert content_approval.parse_callback(None) is None


# === Применение решения ===

@pytest.mark.asyncio
async def test_apply_approve_keeps_schedule():
    """Одобренный черновик с датой возвращается в SCHEDULED, а не в APPROVED:
    иначе он выпадет из напоминаний и фаундер про него забудет."""
    from backend.services import content_factory as svc

    item = _item()
    svc._save([item.model_dump() | {"scheduled_at": "2027-01-01T10:00:00+00:00",
                                    "status": ContentStatus.PENDING_APPROVAL.value}])

    text = await content_approval.apply("approve", item.id)

    updated = svc.get_item(item.id)
    assert updated.status == ContentStatus.SCHEDULED
    assert "01.01" in text or "одобрен" in text.lower()


@pytest.mark.asyncio
async def test_apply_approve_without_schedule():
    from backend.services import content_factory as svc

    item = _item()
    svc._save([item.model_dump() | {"status": ContentStatus.PENDING_APPROVAL.value}])

    await content_approval.apply("approve", item.id)
    assert svc.get_item(item.id).status == ContentStatus.APPROVED


@pytest.mark.asyncio
async def test_apply_reject():
    from backend.services import content_factory as svc

    item = _item()
    svc._save([item.model_dump() | {"status": ContentStatus.PENDING_APPROVAL.value}])

    await content_approval.apply("reject", item.id)
    assert svc.get_item(item.id).status == ContentStatus.REJECTED


@pytest.mark.asyncio
async def test_apply_missing_item_answers_politely():
    """Черновик удалили из интерфейса, а старая кнопка осталась в переписке."""
    from backend.services import content_factory as svc

    svc._save([])
    text = await content_approval.apply("approve", "нет-такого")
    assert "не наш" in text.lower() or "не найден" in text.lower()


# === Текст сообщения с черновиком ===

def test_approval_message_has_essentials():
    text = telegram_notify._draft_summary(_item(scheduled_at="2027-01-01T10:00:00+00:00"))
    assert "утренние ритуалы" in text
    assert "Подпись" in text
    assert "instagram" in text


def test_approval_message_marks_text_only_draft():
    text = telegram_notify._draft_summary(_item())
    assert "только текст" in text


def test_approval_message_lists_ready_media():
    text = telegram_notify._draft_summary(_item(voice_file="a.mp3", image_file="a.jpg"))
    assert "голос" in text and "картинка" in text


# === Отправка ===

@pytest.mark.asyncio
async def test_send_approval_request_posts_buttons(monkeypatch):
    captured: dict = {}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            captured["url"] = url
            captured["json"] = json
            return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(telegram_notify.settings, "telegram_bot_token", "T", raising=False)
    monkeypatch.setattr(telegram_notify.settings, "telegram_allowed_user_id", "42", raising=False)

    ok = await telegram_notify.send_approval_request(_item())

    assert ok is True
    buttons = captured["json"]["reply_markup"]["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == "content:approve:abc12345"
    assert buttons[1]["callback_data"] == "content:reject:abc12345"


@pytest.mark.asyncio
async def test_send_returns_false_without_config(monkeypatch):
    monkeypatch.setattr(telegram_notify.settings, "telegram_bot_token", "", raising=False)
    monkeypatch.setattr(telegram_notify.settings, "telegram_allowed_user_id", "", raising=False)

    assert await telegram_notify.send_approval_request(_item()) is False
