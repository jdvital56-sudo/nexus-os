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
from ..core import eventbus
from . import budget
from . import chat_log
from . import dialog_history
from . import entity_extraction
from . import memory as memory_svc
from . import obsidian
from . import skills as skills_svc
from ..core.config import settings
from .llm import LLMMessage, LLMService
from .memory import MemoryLayer

logger = logging.getLogger(__name__)

# Сколько последних фактов INBOX просматриваем в поисках дубля
_DEDUP_SCAN_LIMIT = 200

# Сколько фактов подмешиваем в запрос — больше не значит лучше,
# длинный контекст размывает ответ и стоит денег
_RECALL_LIMIT = 5

# Порог косинусной близости, выше которого считаем факт повтором
_DEDUP_SIMILARITY = 0.95

# Явный вызов скилла: «/skill publish-post topic=Запуск platform=telegram»
_SKILL_TRIGGER = re.compile(
    r"^\s*(?:/skill|скилл|запусти\s+скилл)\s+(?P<skill_id>[\w-]+)\s*(?P<args>.*)$",
    re.IGNORECASE | re.DOTALL,
)

# Аргументы скилла в виде key=value; значение — до следующего ключа или конца
_SKILL_ARG = re.compile(r"(?P<key>\w+)=(?P<value>.*?)(?=\s+\w+=|$)", re.DOTALL)

# «/note Заголовок | текст» — записать в базу знаний Obsidian
_NOTE_WRITE = re.compile(
    r"^\s*(?:/note|заметка)\s+(?P<title>[^|\n]+?)\s*(?:\||\n)\s*(?P<body>.+)$",
    re.IGNORECASE | re.DOTALL,
)

# «поставь встречу в четверг в 15:00», «запиши в календарь созвон завтра»
# Триггер разбирается без модели: постановка встречи должна быть
# предсказуемой и мгновенной, а не зависеть от настроения LLM
_CALENDAR_TRIGGER = re.compile(
    r"^\s*(?:/встреча|(?:по)?ставь?\s+(?:встречу|созвон|напоминание)|назначь\s+встречу|"
    r"запиши\s+в\s+календарь|добавь\s+в\s+календарь|создай\s+встречу)\s*(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)

# «/notes запрос» — найти в базе знаний
_NOTE_SEARCH = re.compile(
    r"^\s*(?:/notes|найди\s+в\s+заметках)\s+(?P<query>.+)$",
    re.IGNORECASE | re.DOTALL,
)


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
        extract_entities: bool = True,
        use_memory: bool = True,
        use_history: bool = True,
    ):
        self.llm = llm or LLMService()
        self.persona_manager = persona_manager or PersonaManager()
        self.semantic_dedup = semantic_dedup
        self.extract_entities = extract_entities
        self.use_memory = use_memory
        self.use_history = use_history
        self._tasks: set[asyncio.Task] = set()
        # Клиенты под персоны создаются лениво и переиспользуются
        self._llm_cache: dict[tuple[str, str, str], LLMService] = {}

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

        calendar_reply = await self._try_calendar(text)
        if calendar_reply is not None:
            self._emit_message(channel, "user", "Календарь", text)
            self._emit_message(channel, "assistant", "Календарь", calendar_reply)
            await self._log_turn(channel, user_id, text, calendar_reply, "Календарь")
            return calendar_reply

        note_reply = await self._try_note(text)
        if note_reply is not None:
            self._emit_message(channel, "user", "Obsidian", text)
            self._emit_message(channel, "assistant", "Obsidian", note_reply)
            await self._log_turn(channel, user_id, text, note_reply, "Obsidian")
            return note_reply

        skill_reply = await self._try_skill(text)
        if skill_reply is not None:
            self._emit_message(channel, "user", "Skill", text)
            self._emit_message(channel, "assistant", "Skill", skill_reply)
            await self._log_turn(channel, user_id, text, skill_reply, "Skill")
            self._spawn(self._remember(channel, user_id, text, skill_reply, "Skill"))
            return skill_reply

        selected = self._select_persona(text, persona)
        self._emit_message(channel, "user", selected["name"], text)

        llm = self._llm_for(selected, channel=channel)
        context = await asyncio.to_thread(
            self._build_context, text, selected["name"], channel, user_id
        )
        reply = await self._respond(llm, selected["name"], text, context)

        self._emit_message(channel, "assistant", selected["name"], reply)
        # Нить разговора пишется до возврата ответа: следующее сообщение может
        # прийти сразу, и фоновая запись не успела бы за ним
        await self._log_turn(channel, user_id, text, reply, selected["name"])
        self._spawn(self._remember(channel, user_id, text, reply, selected["name"]))
        self._spawn(self._extract(channel, user_id, text, reply, llm))
        return reply

    async def _respond(
        self, llm: LLMService, persona_name: str, text: str, context: str
    ) -> str:
        """Ответ персоны. С инструментами — если ей они положены.

        Персонам, которым веб не нужен (код, глубокий разбор), инструменты не
        предлагаем вовсе: лишний вызов стоит денег, а модель, увидев поиск,
        тянется его позвать даже там, где ответ она знает.
        """
        from . import tools as tools_svc

        # Проверяем ЗДЕСЬ, не только внутри chat_with_tools: её запасной путь
        # дёргает llm.chat() — метод, которого нет ни у Anthropic/Gemini
        # веток, ни у тестовых дублёров LLM, только generate_response().
        # Дойти до неё с такой моделью — значит упасть чуть позже и непонятнее.
        available = tools_svc.tools_for(persona_name)
        if not available or not tools_svc.supports_tools(llm):
            return await llm.generate_response(text, context=context, kind=budget.INTERACTIVE)

        # Собираем запрос ровно как generate_response, чтобы ответы с
        # инструментами и без них не расходились по форме
        full_prompt = f"Context: {context}\n\nUser: {text}\n\nAssistant:"
        response = await tools_svc.chat_with_tools(
            llm,
            [LLMMessage(role="user", content=full_prompt)],
            tools=available,
            temperature=0.7,
            max_tokens=settings.max_reply_tokens,
            kind=budget.INTERACTIVE,
        )
        return response.content

    async def _log_turn(
        self, channel: str, user_id: str, text: str, reply: str, persona: str
    ) -> None:
        """Кладёт пару реплик в короткую память. Сбой не должен ломать диалог."""
        if not self.use_history:
            return
        try:
            await asyncio.to_thread(
                dialog_history.append_turn, channel, user_id, text, reply, persona
            )
            # Полная лента — то, что человек читает на экране. Буфер выше
            # режется до 600 символов ради промпта, и длинные ответы в чате
            # обрывались на полуслове
            await asyncio.to_thread(
                chat_log.append_turn,
                channel,
                user_id,
                [("user", text, ""), ("assistant", reply, persona)],
            )
        except Exception:
            logger.exception("Не удалось записать историю диалога %s:%s", channel, user_id)

    def _build_context(
        self, text: str, persona_name: str, channel: str = "", user_id: str = ""
    ) -> str:
        """Подмешивает в запрос то, что система уже знает.

        Без этого Hermes писал бы в память, но никогда из неё не читал —
        каждое сообщение обрабатывалось бы с чистого листа.
        """
        parts = [f"Persona: {persona_name}"]

        if self.use_memory:
            try:
                facts = memory_svc.recall(text, limit=_RECALL_LIMIT)
            except Exception:
                logger.debug("Recall недоступен", exc_info=True)
                facts = []

            if facts:
                known = "\n".join(f"- {f.content[:300]}" for f in facts)
                parts.append(
                    "Что тебе уже известно из памяти (используй, если уместно; "
                    "не ссылайся на «память» вслух):\n" + known
                )

            # База знаний Obsidian — то, что фаундер написал сам
            vault = obsidian.context_for(text)
            if vault:
                parts.append(vault)

        # Нить разговора идёт последней: она ближе всего к самому вопросу,
        # а «переделай короче» относится именно к ней, не к фактам из памяти
        thread = self._history_block(channel, user_id)
        if thread:
            parts.append(thread)

        return "\n\n".join(parts)

    def _history_block(self, channel: str, user_id: str) -> str:
        """Последние реплики этого канала. Недоступность истории не критична."""
        if not self.use_history or not channel:
            return ""
        try:
            return dialog_history.render(channel, user_id)
        except Exception:
            logger.debug("История диалога недоступна", exc_info=True)
            return ""

    @staticmethod
    def _emit_message(channel: str, role: str, persona: str, text: str) -> None:
        """Сообщение в поток Activity — целиком текст туда не уходит (§3)."""
        source = eventbus.SOURCE_HERMES if channel == "telegram" else eventbus.SOURCE_WEB
        eventbus.emit(
            eventbus.CHAT_MESSAGE,
            {
                "channel": channel,
                "role": role,
                "persona": persona,
                "text_preview": text[:120],
            },
            source=source,
        )

    async def _extract(
        self, channel: str, user_id: str, text: str, reply: str, llm: Any = None
    ) -> None:
        """Достаёт сущности из диалога в граф. Тихо уступает бюджету (I-4).

        Работает тем же клиентом, который только что ответил: клиент по
        умолчанию может смотреть в незапущенную локальную модель, и тогда
        фоновая задача падала бы на каждом сообщении.
        """
        if not self.extract_entities:
            return
        try:
            result = await entity_extraction.extract_from_dialog(
                llm or self.llm,
                text,
                reply,
                source=f"{channel}:{user_id}",
                semantic=self.semantic_dedup,
            )
            if result["nodes_added"] or result["edges_added"]:
                logger.info(
                    "Граф пополнен из %s: +%d узлов, +%d рёбер",
                    channel,
                    result["nodes_added"],
                    result["edges_added"],
                )
        except budget.BudgetExceeded as e:
            logger.warning("Извлечение сущностей отложено: %s", e)
        except Exception:
            logger.exception("Извлечение сущностей из %s не удалось", channel)

    async def _try_calendar(self, text: str) -> str | None:
        """Ставит встречу по фразе. Не команда — возвращает None.

        Время разбирается кодом, а не моделью: «в четверг в 15:00» должно
        попадать в четверг в 15:00 всегда, а не с вероятностью. И отвечаем
        человеческой датой, чтобы ошибку было видно сразу, а не на встрече.
        """
        match = _CALENDAR_TRIGGER.match(text)
        if not match:
            return None

        rest = (match.group("rest") or "").strip()
        if not rest:
            return "Скажи, что и когда поставить: «поставь встречу с Ольгой завтра в 15:00»."

        from . import calendar as calendar_svc
        from . import when_ru

        moment = when_ru.parse(rest)
        if moment is None:
            return (
                f"Не понял, когда именно. Скажи со временем: «{rest} завтра в 15:00»."
            )

        title = moment.text or "Встреча"
        try:
            event = await asyncio.to_thread(
                calendar_svc.create_event, title, moment.start, moment.duration_minutes
            )
        except calendar_svc.CalendarNotConnected as e:
            return f"📅 {e}"
        except Exception as e:
            logger.exception("Не удалось создать событие")
            return f"Не удалось поставить встречу: {e}"

        when = when_ru.human(moment.start)
        tail = "" if moment.explicit_time else " (время не назвал — поставил на 10:00)"
        return f"📅 Поставил: «{title}» {when}{tail}."

    async def _try_note(self, text: str) -> str | None:
        """Работа с базой знаний из диалога. Не команда — возвращает None.

        Запись в чужое хранилище — заметное действие, поэтому она делается
        только по явной команде, а не по догадке модели.
        """
        match = _NOTE_WRITE.match(text)
        if match:
            title = match.group("title").strip()
            body = (match.group("body") or "").strip()
            if not body:
                return "Нужен текст заметки: /note Заголовок | текст заметки"
            try:
                result = await asyncio.to_thread(obsidian.write_note, title, body)
            except obsidian.VaultNotConfigured as e:
                return f"📓 {e}"
            except Exception as e:
                logger.exception("Не удалось записать заметку")
                return f"Не удалось записать заметку: {e}"
            verb = "создана" if result["action"] == "created" else "дополнена"
            return f"📓 Заметка {verb}: {result['path']}"

        match = _NOTE_SEARCH.match(text)
        if match:
            query = match.group("query").strip()
            try:
                notes = await asyncio.to_thread(obsidian.search_notes, query)
            except obsidian.VaultNotConfigured as e:
                return f"📓 {e}"
            except Exception as e:
                logger.exception("Поиск по хранилищу упал")
                return f"Поиск не удался: {e}"
            if not notes:
                return f"📓 По запросу «{query}» в базе знаний ничего нет."
            lines = [f"📓 Нашёл в базе знаний ({len(notes)}):"]
            for n in notes:
                lines.append(f"- {n['title']} ({n['path']})")
            return "\n".join(lines)

        return None

    async def _try_skill(self, text: str) -> str | None:
        """Исполняет скилл, если сообщение — явный вызов. Иначе None.

        Триггер разбирается без LLM: вызов скилла должен быть предсказуемым
        и не стоить денег.
        """
        match = _SKILL_TRIGGER.match(text)
        if not match:
            return None

        skill_id = match.group("skill_id")
        params = {
            m.group("key"): m.group("value").strip()
            for m in _SKILL_ARG.finditer(match.group("args") or "")
        }

        try:
            result = await asyncio.to_thread(skills_svc.execute_skill, skill_id, params)
        except FileNotFoundError:
            available = await asyncio.to_thread(skills_svc.list_skills)
            names = ", ".join(s["id"] for s in available) or "нет ни одного"
            return f"Скилл «{skill_id}» не найден. Доступные: {names}"
        except Exception as e:
            logger.exception("Скилл %s упал", skill_id)
            return f"Скилл «{skill_id}» завершился с ошибкой: {e}"

        return self._format_skill_result(result)

    @staticmethod
    def _format_skill_result(result: dict[str, Any]) -> str:
        """Человекочитаемый отчёт: что именно сделал скилл."""
        lines = [f"Скилл «{result['skill_name']}» выполнен."]
        for entry in result.get("log", []):
            status = entry.get("status")
            action = entry.get("action")
            if status == "ok":
                detail = entry.get("result") or {}
                summary = ", ".join(f"{k}={v}" for k, v in detail.items())
                lines.append(f"  • {action}: {summary}" if summary else f"  • {action}")
            elif status == "skipped":
                lines.append(f"  • {action}: пропущен")
            else:
                lines.append(f"  • {action}: ошибка — {entry.get('error')}")
        return "\n".join(lines)

    def _llm_for(self, persona: dict[str, Any], channel: str = "") -> LLMService:
        """Клиент под персону: своя модель на каждое сообщение.

        Если у провайдера персоны нет ключа, откатываемся на общий клиент —
        иначе диалог сломается из-за незаполненного .env.
        """
        config = self.persona_manager.get_model_config(persona)
        config["system_prompt"] = self._compose_prompt(config["system_prompt"])
        provider = config["provider"]
        if provider != "ollama" and not config.get("api_key"):
            logger.info(
                "%s: персона %s -> клиент по умолчанию (нет ключа для %s)",
                channel or "-",
                persona["name"],
                provider,
            )
            return self.llm

        logger.info(
            "%s: персона %s -> %s/%s",
            channel or "-",
            persona["name"],
            provider,
            config["model"],
        )
        # Промпт входит в ключ: правка из Mission Control обязана долететь до
        # следующего сообщения, а не остаться в закэшированном клиенте
        key = (provider, config["model"], config["system_prompt"])
        if key not in self._llm_cache:
            self._llm_cache[key] = LLMService(
                provider=provider,
                model=config["model"],
                api_key=config["api_key"],
                base_url=config["base_url"],
                system_prompt=config["system_prompt"],
            )
        return self._llm_cache[key]

    @staticmethod
    def _compose_prompt(persona_prompt: str) -> str:
        """Собирает промпт: общие правила, характер, затем сама персона.

        Характер идёт последним из общего — он ближе к персоне и уточняет
        её, а не спорит с ней. Ползунки из Пантеона попадают сюда текстом.
        """
        try:
            from . import personas as persona_store

            common = persona_store.get_system_prompt()
            character = persona_store.describe_character(persona_store.get_character())
        except Exception:
            logger.debug("Системный промпт недоступен", exc_info=True)
            return persona_prompt

        parts = [p for p in (common, character, persona_prompt) if p]
        return "\n\n".join(parts)

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
