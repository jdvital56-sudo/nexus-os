"""Единый контур мышления Nexus OS.

Пайплайн «персона → память → LLM» живёт здесь и только здесь (инвариант I-1).
Telegram, веб-чат и голос — тонкие адаптеры, которые зовут `handle()`.
Второй «мозг» не заводится ни под каким предлогом.
"""
import asyncio
import hashlib
import logging
import re
from typing import Any

from ..agents.persona_manager import PersonaManager
from . import memory as memory_svc
from .llm import LLMService
from .memory import MemoryLayer

logger = logging.getLogger(__name__)

# Сколько последних фактов INBOX просматриваем в поисках дубля
_DEDUP_SCAN_LIMIT = 200

# Порог косинусной близости, выше которого считаем факт повтором
_DEDUP_SIMILARITY = 0.95


def _normalize(text: str) -> str:
    """Схлопывает регистр и пробелы — чтобы «Привет!» и «привет !» дали один хэш."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _content_hash(text: str) -> str:
    return hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()[:16]


class ConversationService:
    """Обрабатывает одно сообщение пользователя из любого канала."""

    def __init__(
        self,
        llm: LLMService | None = None,
        persona_manager: PersonaManager | None = None,
        *,
        semantic_dedup: bool = True,
    ):
        self.llm = llm or LLMService()
        self.persona_manager = persona_manager or PersonaManager()
        self.semantic_dedup = semantic_dedup
        self._tasks: set[asyncio.Task] = set()

    async def handle(
        self,
        channel: str,
        user_id: str,
        text: str,
        persona: str | None = None,
    ) -> str:
        """Принимает сообщение, возвращает ответ.

        Запись в память идёт фоном уже после того, как ответ готов (I-5),
        поэтому латентность канала от неё не зависит.
        """
        if not text or not text.strip():
            raise ValueError("Пустое сообщение")

        selected = self._select_persona(text, persona)
        reply = await self.llm.generate_response(
            text, context=f"Persona: {selected['name']}"
        )

        self._spawn(self._remember(channel, user_id, text, reply, selected["name"]))
        return reply

    def _select_persona(self, text: str, persona: str | None) -> dict[str, Any]:
        """Явно заданная персона важнее автоопределения."""
        if persona:
            found = self.persona_manager.get_persona(persona)
            if found:
                return found
            logger.warning("Персона '%s' не найдена, определяю автоматически", persona)
        return self.persona_manager.detect_persona(text)

    def _spawn(self, coro) -> None:
        """Запускает фоновую задачу, удерживая ссылку — иначе GC может её съесть."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """Дожидается фоновых записей — для тестов и корректного завершения."""
        while self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    async def _remember(
        self, channel: str, user_id: str, text: str, reply: str, persona: str
    ) -> None:
        """Кладёт пару «сообщение/ответ» в INBOX (I-2). Ошибки не роняют диалог."""
        content = f"Пользователь: {text}\n{persona}: {reply}"
        source = f"{channel}:{user_id}"
        try:
            if await asyncio.to_thread(self._is_duplicate, content):
                logger.debug("Дубль факта из %s пропущен", source)
                return
            fact = await asyncio.to_thread(
                memory_svc.add_fact,
                content,
                MemoryLayer.INBOX,
                source,
                0.5,
                None,
                ["dialog", channel, persona.lower()],
            )
            await asyncio.to_thread(self._index_fact, fact)
        except Exception:
            logger.exception("Не удалось записать факт из %s в память", source)

    def _is_duplicate(self, content: str) -> bool:
        """Хэш нормализованного текста, затем — семантическая близость (I-2)."""
        target = _content_hash(content)
        recent = memory_svc.get_facts(
            layer=MemoryLayer.INBOX, limit=_DEDUP_SCAN_LIMIT
        )
        if any(_content_hash(f.content) == target for f in recent):
            return True

        if not self.semantic_dedup:
            return False
        try:
            from .vector_store import search_vectors

            hits = search_vectors(content, limit=3, min_score=_DEDUP_SIMILARITY)
            return any(h["id"].startswith("memory:") for h in hits)
        except Exception:
            logger.debug("Семантический дедуп недоступен", exc_info=True)
            return False

    def _index_fact(self, fact: memory_svc.MemoryFact) -> None:
        """Индексирует факт, чтобы работали recall() и семантический дедуп."""
        if not self.semantic_dedup:
            return
        try:
            from .vector_store import add_vector

            add_vector(
                f"memory:{fact.id}",
                f"[{fact.source}] {fact.content}",
                {"type": "memory", "layer": fact.layer.value, "confidence": fact.confidence},
            )
        except Exception:
            logger.debug("Не удалось проиндексировать факт %s", fact.id, exc_info=True)


_service: ConversationService | None = None


def get_conversation_service() -> ConversationService:
    """Общий экземпляр для адаптеров (Telegram, веб, голос)."""
    global _service
    if _service is None:
        _service = ConversationService()
    return _service
