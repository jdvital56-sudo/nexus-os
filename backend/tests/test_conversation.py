"""Тесты единого контура мышления — мимо Telegram (I-1)."""
import asyncio

import pytest

from backend.services import memory as mem_svc
from backend.services.conversation import ConversationService
from backend.services.memory import MemoryLayer


class FakeLLM:
    """Подменяет LLMService: запоминает вызовы, отвечает предсказуемо."""

    def __init__(self, reply: str = "ответ модели"):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    async def generate_response(self, user_message: str, context: str = "") -> str:
        self.calls.append((user_message, context))
        return self.reply


def make_service(llm: FakeLLM | None = None) -> ConversationService:
    # semantic_dedup=False — тесты не должны зависеть от векторного стора
    return ConversationService(llm=llm or FakeLLM(), semantic_dedup=False)


@pytest.mark.asyncio
async def test_handle_returns_llm_reply():
    llm = FakeLLM("привет из модели")
    svc = make_service(llm)

    reply = await svc.handle("telegram", "42", "как дела?")
    await svc.drain()

    assert reply == "привет из модели"
    assert llm.calls[0][0] == "как дела?"


@pytest.mark.asyncio
async def test_message_is_written_to_inbox():
    svc = make_service(FakeLLM("ответ"))

    await svc.handle("telegram", "42", "запомни это")
    await svc.drain()

    facts = mem_svc.get_facts(layer=MemoryLayer.INBOX)
    assert len(facts) == 1
    assert "запомни это" in facts[0].content
    assert "ответ" in facts[0].content
    assert facts[0].source == "telegram:42"
    assert "dialog" in facts[0].tags
    assert "telegram" in facts[0].tags


@pytest.mark.asyncio
async def test_duplicate_message_is_not_stored_twice():
    svc = make_service(FakeLLM("один и тот же ответ"))

    await svc.handle("telegram", "42", "повтор")
    await svc.drain()
    # Тот же текст с другим регистром и пробелами — тот же нормализованный хэш
    await svc.handle("telegram", "42", "  ПОВТОР  ")
    await svc.drain()

    assert len(mem_svc.get_facts(layer=MemoryLayer.INBOX)) == 1


@pytest.mark.asyncio
async def test_automatic_persona_detection_reaches_llm():
    llm = FakeLLM()
    svc = make_service(llm)

    await svc.handle("telegram", "42", "напиши код на python")
    await svc.drain()

    # «код» — ключевое слово Architect
    assert "Architect" in llm.calls[0][1]


@pytest.mark.asyncio
async def test_explicit_persona_overrides_detection():
    llm = FakeLLM()
    svc = make_service(llm)

    await svc.handle("web", "42", "напиши код", persona="Philosopher")
    await svc.drain()

    assert "Philosopher" in llm.calls[0][1]


@pytest.mark.asyncio
async def test_unknown_persona_falls_back_to_detection():
    llm = FakeLLM()
    svc = make_service(llm)

    await svc.handle("web", "42", "напиши код", persona="НетТакой")
    await svc.drain()

    assert "Architect" in llm.calls[0][1]


@pytest.mark.asyncio
async def test_empty_message_rejected():
    svc = make_service()

    with pytest.raises(ValueError):
        await svc.handle("telegram", "42", "   ")


@pytest.mark.asyncio
async def test_channel_is_recorded_per_source():
    svc = make_service(FakeLLM("ответ"))

    await svc.handle("web", "user-7", "сообщение с сайта")
    await svc.drain()

    fact = mem_svc.get_facts(layer=MemoryLayer.INBOX)[0]
    assert fact.source == "web:user-7"
    assert "web" in fact.tags


@pytest.mark.asyncio
async def test_reply_does_not_wait_for_memory_write(monkeypatch):
    """Ответ уходит пользователю раньше, чем факт ляжет в память (I-5)."""
    started = asyncio.Event()
    release = asyncio.Event()
    original_add_fact = mem_svc.add_fact

    def slow_add_fact(*args, **kwargs):
        started.set()
        # Блокируем поток записи, пока тест не разрешит продолжить
        asyncio.run(asyncio.wait_for(release.wait(), timeout=5))
        return original_add_fact(*args, **kwargs)

    monkeypatch.setattr(mem_svc, "add_fact", slow_add_fact)
    svc = make_service(FakeLLM("быстрый ответ"))

    reply = await svc.handle("telegram", "42", "сообщение")

    # Ответ уже есть, а запись ещё не завершилась
    assert reply == "быстрый ответ"
    assert mem_svc.get_facts(layer=MemoryLayer.INBOX) == []

    release.set()
    await svc.drain()


@pytest.mark.asyncio
async def test_memory_failure_does_not_break_dialog(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("память недоступна")

    monkeypatch.setattr(mem_svc, "add_fact", boom)
    svc = make_service(FakeLLM("ответ несмотря ни на что"))

    reply = await svc.handle("telegram", "42", "сообщение")
    await svc.drain()

    assert reply == "ответ несмотря ни на что"
