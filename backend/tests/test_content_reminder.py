"""Напоминание «пора постить»: тик планировщика по назначенным черновикам.

Система сама никуда не публикует (решение фаундера) — в назначенный час
она только пишет в Telegram, что пора, и черновик остаётся ждать, пока
фаундер не отметит его опубликованным вручную.
"""
from datetime import datetime, timedelta, timezone

import pytest

from backend.models.schemas import ContentStatus
from backend.services import content_factory as svc
from backend.services import content_reminder


class StubLLM:
    async def generate_response(self, user_message, context="", kind="interactive", json_mode=False):
        return '[{"script": "Сценарий", "caption": "Подпись", "hashtags": []}]'


async def _scheduled_draft(when: datetime):
    items = await svc.generate_plan("тема", count=1, llm=StubLLM())
    item = items[0]
    # schedule_item отвергает прошедшую дату — ставим будущую и подменяем
    # в хранилище, чтобы получить «уже наступивший» срок без ожидания.
    svc.schedule_item(item.id, (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    raw = svc._load()
    for i in raw:
        if i["id"] == item.id:
            i["scheduled_at"] = when.isoformat()
    svc._save(raw)
    return item


@pytest.mark.asyncio
async def test_tick_notifies_due_draft(monkeypatch):
    sent: list[str] = []

    async def fake_reminder(item):
        sent.append(item.id)
        return True

    monkeypatch.setattr(content_reminder.telegram_notify, "send_publish_reminder", fake_reminder)

    item = await _scheduled_draft(datetime.now(timezone.utc) - timedelta(minutes=5))
    await content_reminder.tick()

    assert sent == [item.id]


@pytest.mark.asyncio
async def test_tick_does_not_repeat_reminder(monkeypatch):
    """Второй тик по тому же черновику молчит.

    Планировщик тикает каждые несколько минут, а срок остаётся прошедшим
    навсегда — без отметки об отправке фаундер получал бы одно и то же
    напоминание до самой публикации.
    """
    sent: list[str] = []

    async def fake_reminder(item):
        sent.append(item.id)
        return True

    monkeypatch.setattr(content_reminder.telegram_notify, "send_publish_reminder", fake_reminder)

    await _scheduled_draft(datetime.now(timezone.utc) - timedelta(minutes=5))
    await content_reminder.tick()
    await content_reminder.tick()

    assert len(sent) == 1


@pytest.mark.asyncio
async def test_tick_retries_when_telegram_failed(monkeypatch):
    """Не ушло — не считаем напомненным, попробуем на следующем тике."""
    attempts: list[str] = []

    async def failing_reminder(item):
        attempts.append(item.id)
        return False

    monkeypatch.setattr(content_reminder.telegram_notify, "send_publish_reminder", failing_reminder)

    await _scheduled_draft(datetime.now(timezone.utc) - timedelta(minutes=5))
    await content_reminder.tick()
    await content_reminder.tick()

    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_tick_quiet_when_nothing_due(monkeypatch):
    sent: list[str] = []

    async def fake_reminder(item):
        sent.append(item.id)
        return True

    monkeypatch.setattr(content_reminder.telegram_notify, "send_publish_reminder", fake_reminder)

    items = await svc.generate_plan("тема", count=1, llm=StubLLM())
    svc.schedule_item(items[0].id, (datetime.now(timezone.utc) + timedelta(days=5)).isoformat())

    await content_reminder.tick()
    assert sent == []


@pytest.mark.asyncio
async def test_reminded_draft_stays_scheduled(monkeypatch):
    """Напомнили — но черновик не «опубликован»: это делает человек."""
    async def fake_reminder(item):
        return True

    monkeypatch.setattr(content_reminder.telegram_notify, "send_publish_reminder", fake_reminder)

    item = await _scheduled_draft(datetime.now(timezone.utc) - timedelta(minutes=5))
    await content_reminder.tick()

    assert svc.get_item(item.id).status == ContentStatus.SCHEDULED
