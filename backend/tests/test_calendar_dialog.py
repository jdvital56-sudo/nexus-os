"""Постановка встречи голосом: «поставь встречу в четверг в 15:00».

До этого календарь умел только читать, а создание события всегда ставило
его «сейчас» — сказать «на четверг» было невозможно в принципе.
"""
from datetime import datetime

import pytest

from backend.services import calendar as calendar_svc
from backend.services.conversation import ConversationService


class FakeLLM:
    def __init__(self):
        self.calls = []

    async def generate_response(self, user_message, context="", kind="interactive", json_mode=False):
        self.calls.append(user_message)
        return "модель не должна отвечать на команду календаря"


def make_service():
    return ConversationService(llm=FakeLLM(), semantic_dedup=False, extract_entities=False)


@pytest.fixture
def created(monkeypatch):
    """Подменяем Google: тесты не ходят в чужой календарь."""
    box = {}

    def fake_create(summary, start, duration_minutes=60, description=""):
        box.update(summary=summary, start=start, duration=duration_minutes)
        return {"id": "ev1", "summary": summary, "start": start.isoformat()}

    monkeypatch.setattr(calendar_svc, "create_event", fake_create)
    return box


@pytest.mark.asyncio
async def test_meeting_is_created_from_speech(created):
    svc = make_service()

    reply = await svc.handle("web", "founder", "поставь встречу с Ольгой завтра в 15:00")
    await svc.drain()

    assert created["summary"] == "с Ольгой"
    assert (created["start"].hour, created["start"].minute) == (15, 0)
    assert "Поставил" in reply


@pytest.mark.asyncio
async def test_model_is_not_called_for_calendar(created):
    """Команда календаря не должна стоить денег."""
    llm = FakeLLM()
    svc = ConversationService(llm=llm, semantic_dedup=False, extract_entities=False)

    await svc.handle("web", "founder", "запиши в календарь созвон завтра в 11")
    await svc.drain()

    assert llm.calls == []


@pytest.mark.asyncio
async def test_reply_names_the_day_in_words(created):
    """Человек должен увидеть ошибку сразу, а не на встрече."""
    svc = make_service()

    reply = await svc.handle("web", "founder", "назначь встречу в четверг в 9:30")
    await svc.drain()

    assert "четверг" in reply and "09:30" in reply


@pytest.mark.asyncio
async def test_missing_time_is_asked_about(created):
    svc = make_service()

    reply = await svc.handle("web", "founder", "поставь встречу с подрядчиком")
    await svc.drain()

    assert "когда" in reply.lower()
    assert "summary" not in created


@pytest.mark.asyncio
async def test_disconnected_calendar_says_why(monkeypatch):
    def not_connected(*args, **kwargs):
        raise calendar_svc.CalendarNotConnected("Google Calendar не подключён: нет файла доступа")

    monkeypatch.setattr(calendar_svc, "create_event", not_connected)
    svc = make_service()

    reply = await svc.handle("web", "founder", "поставь встречу завтра в 12")
    await svc.drain()

    assert "не подключён" in reply


@pytest.mark.asyncio
async def test_ordinary_message_is_not_a_calendar_command(created):
    """Слово «встреча» в разговоре не должно ничего ставить."""
    svc = make_service()

    reply = await svc.handle("web", "founder", "расскажи, как прошла встреча вчера")
    await svc.drain()

    assert "Поставил" not in reply
    assert "summary" not in created


@pytest.mark.asyncio
async def test_date_without_time_gets_default_and_says_so(created):
    svc = make_service()

    reply = await svc.handle("web", "founder", "поставь встречу с юристом в пятницу")
    await svc.drain()

    assert created["start"].hour == 10
    assert "10:00" in reply
