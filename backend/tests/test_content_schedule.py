"""Расписание Content Factory: дата публикации, площадки, статусы, напоминания.

Спецификация фаундера 23.08.2026 (допрос по семи пунктам): у черновика есть
одно общее время публикации на все площадки, approve приходит кнопкой в
Telegram, а в назначенный час система напоминает «пора постить» — сама она
никуда не публикует.
"""
from datetime import datetime, timedelta, timezone

import pytest

from backend.core.errors import NotFoundError, ValidationError
from backend.models.schemas import ContentStatus
from backend.services import content_factory as svc


class StubLLM:
    async def generate_response(self, user_message, context="", kind="interactive", json_mode=False):
        return '[{"script": "Сценарий", "caption": "Подпись", "hashtags": ["a"]}]'


async def _one_draft(**kwargs):
    items = await svc.generate_plan("тема", count=1, llm=StubLLM(), **kwargs)
    return items[0]


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# === Постановка в расписание ===

@pytest.mark.asyncio
async def test_schedule_sets_date_and_status():
    item = await _one_draft()
    when = _iso(datetime.now(timezone.utc) + timedelta(days=1))

    updated = svc.schedule_item(item.id, when)

    assert updated.scheduled_at == when
    assert updated.status == ContentStatus.SCHEDULED


@pytest.mark.asyncio
async def test_schedule_rejects_garbage_date():
    item = await _one_draft()
    with pytest.raises(ValidationError):
        svc.schedule_item(item.id, "когда-нибудь во вторник")


@pytest.mark.asyncio
async def test_schedule_rejects_past_date():
    """Прошедшая дата — почти всегда обмолвка или сбитый разбор фразы.

    Молча принять её значит, что напоминание не придёт никогда: due_items
    отдаст черновик сразу, ещё до того, как фаундер успеет его посмотреть.
    """
    item = await _one_draft()
    past = _iso(datetime.now(timezone.utc) - timedelta(days=2))
    with pytest.raises(ValidationError):
        svc.schedule_item(item.id, past)


@pytest.mark.asyncio
async def test_schedule_unknown_item():
    with pytest.raises(NotFoundError):
        svc.schedule_item("нет-такого", _iso(datetime.now(timezone.utc) + timedelta(days=1)))


# === Площадки ===

@pytest.mark.asyncio
async def test_set_platforms_replaces_list():
    item = await _one_draft(platforms=["tiktok"])
    updated = svc.set_platforms(item.id, ["instagram", "youtube"])
    assert updated.platforms == ["instagram", "youtube"]


@pytest.mark.asyncio
async def test_set_platforms_rejects_empty():
    item = await _one_draft()
    with pytest.raises(ValidationError):
        svc.set_platforms(item.id, [])


# === Отметка «опубликовано» ===

@pytest.mark.asyncio
async def test_mark_posted():
    item = await _one_draft()
    svc.schedule_item(item.id, _iso(datetime.now(timezone.utc) + timedelta(hours=2)))
    updated = svc.mark_posted(item.id)
    assert updated.status == ContentStatus.POSTED


# === Что пора напомнить ===

@pytest.mark.asyncio
async def test_due_items_returns_only_ripe_scheduled():
    now = datetime.now(timezone.utc)

    ripe = await _one_draft()
    svc.schedule_item(ripe.id, _iso(now + timedelta(hours=1)))

    later = await _one_draft()
    svc.schedule_item(later.id, _iso(now + timedelta(days=3)))

    draft_only = await _one_draft()  # без расписания вообще

    due = svc.due_items(now=now + timedelta(hours=2))
    due_ids = {i.id for i in due}

    assert ripe.id in due_ids
    assert later.id not in due_ids
    assert draft_only.id not in due_ids


@pytest.mark.asyncio
async def test_due_items_skips_already_posted():
    """Напоминание не должно приходить второй раз про то, что уже вышло."""
    now = datetime.now(timezone.utc)
    item = await _one_draft()
    svc.schedule_item(item.id, _iso(now + timedelta(hours=1)))
    svc.mark_posted(item.id)

    assert svc.due_items(now=now + timedelta(hours=2)) == []


@pytest.mark.asyncio
async def test_due_items_skips_rejected():
    now = datetime.now(timezone.utc)
    item = await _one_draft()
    svc.schedule_item(item.id, _iso(now + timedelta(hours=1)))
    svc.set_status(item.id, ContentStatus.REJECTED)

    assert svc.due_items(now=now + timedelta(hours=2)) == []


# === Отправка на подтверждение ===

@pytest.mark.asyncio
async def test_send_for_approval_sets_pending(monkeypatch):
    sent: list[dict] = []

    async def fake_send(item, **kwargs):
        sent.append({"id": item.id})
        return True

    from backend.services import telegram_notify

    monkeypatch.setattr(telegram_notify, "send_approval_request", fake_send)

    item = await _one_draft()
    updated = await svc.send_for_approval(item.id)

    assert updated.status == ContentStatus.PENDING_APPROVAL
    assert sent and sent[0]["id"] == item.id


@pytest.mark.asyncio
async def test_send_for_approval_keeps_draft_when_telegram_silent(monkeypatch):
    """Телеграм не настроен — черновик обязан остаться DRAFT.

    Иначе он навсегда зависнет в «ждёт подтверждения», которого физически
    некому дать: сообщение с кнопками никуда не ушло.
    """
    async def fake_send(item, **kwargs):
        return False

    from backend.services import telegram_notify

    monkeypatch.setattr(telegram_notify, "send_approval_request", fake_send)

    item = await _one_draft()
    updated = await svc.send_for_approval(item.id)

    assert updated.status == ContentStatus.DRAFT
