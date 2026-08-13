"""Тесты единого контура мышления — мимо Telegram (I-1)."""
import asyncio

import pytest

from backend.services import memory as mem_svc
from backend.services.conversation import ConversationService
from backend.services.memory import MemoryLayer
from backend.services import budget as budget_mod


class FakeLLM:
    """Подменяет LLMService: запоминает вызовы, отвечает предсказуемо."""

    def __init__(self, reply: str = "ответ модели"):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []
        self.system_prompt = ""
        # Критик (Сехмет/Philosopher) зовёт chat() напрямую — по умолчанию
        # всегда PASS, чтобы остальные тесты его не замечали
        self.chat_calls: list[list] = []
        self.chat_reply = "PASS"

    async def generate_response(
        self, user_message: str, context: str = "", kind: str = "interactive"
    ) -> str:
        self.calls.append((user_message, context))
        return self.reply

    async def chat(self, messages, temperature=0.7, max_tokens=1024, stream=False, kind="interactive", json_mode=False):
        from backend.services.llm import LLMResponse

        self.chat_calls.append(messages)
        return LLMResponse(content=self.chat_reply, model="fake")


def make_service(llm: FakeLLM | None = None, extract_entities: bool = False) -> ConversationService:
    # semantic_dedup=False — тесты не должны зависеть от векторного стора
    return ConversationService(
        llm=llm or FakeLLM(),
        semantic_dedup=False,
        extract_entities=extract_entities,
    )


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


class RecordingLLM(FakeLLM):
    """Помнит, с каким kind его звали."""

    def __init__(self, reply: str = "ответ"):
        super().__init__(reply)
        self.kinds: list[str] = []

    async def generate_response(
        self, user_message: str, context: str = "", kind: str = "interactive"
    ) -> str:
        self.kinds.append(kind)
        return await super().generate_response(user_message, context, kind)


def with_provider_keys(monkeypatch):
    """Как будто ключи Пантеона заполнены в .env."""
    from backend.core.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    monkeypatch.setattr(settings, "openai_api_key", "sk-openai-test")
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-deepseek-test")


@pytest.mark.asyncio
async def test_personas_resolve_to_different_models(monkeypatch):
    """Ключевой DoD PR-5: разные персоны — разные model-id."""
    with_provider_keys(monkeypatch)
    svc = make_service()

    # Сверяемся с настройками персоны, а не с зашитой строкой: раньше здесь
    # стояли конкретные model-id, и тест пережил их отключение провайдером —
    # `claude-3-opus-20240229` Anthropic отключила, а `claude-3.5-sonnet`
    # вообще не был правильным идентификатором. Проверять надо проводку
    # «настройка персоны → клиент», а не помнить имя модели наизусть.
    for name in ("Architect", "Philosopher", "Labyrinth"):
        persona = svc.persona_manager.get_persona(name)
        client = svc._llm_for(persona)
        assert client.model == persona["model"]
        assert client.provider == persona["provider"]

    philosopher = svc.persona_manager.get_persona("Philosopher")
    architect = svc.persona_manager.get_persona("Architect")
    assert philosopher["model"] != architect["model"], (
        "Философа держим на отдельной модели: он вызывается редко и по дорогим решениям"
    )


@pytest.mark.asyncio
async def test_persona_system_prompt_reaches_client(monkeypatch):
    with_provider_keys(monkeypatch)
    svc = make_service()

    persona = svc.persona_manager.get_persona("Architect")
    client = svc._llm_for(persona)
    # Сверяем с промптом самой персоны, а не ищем в нём её имя: развёрнутые
    # промпты описывают работу, а не представляются («Ты Architect...»)
    assert persona["system_prompt"] in client.system_prompt


@pytest.mark.asyncio
async def test_deepseek_persona_gets_its_own_base_url(monkeypatch):
    with_provider_keys(monkeypatch)
    svc = make_service()

    orpheus = svc._llm_for(svc.persona_manager.get_persona("Orpheus"))
    assert orpheus.provider == "deepseek"
    assert "deepseek" in orpheus.base_url


@pytest.mark.asyncio
async def test_clients_are_reused_per_persona(monkeypatch):
    with_provider_keys(monkeypatch)
    svc = make_service()
    persona = svc.persona_manager.get_persona("Architect")

    assert svc._llm_for(persona) is svc._llm_for(persona)


@pytest.mark.asyncio
async def test_persona_without_api_key_falls_back_to_default_client(monkeypatch):
    """Незаполненный .env не должен ломать диалог."""
    from backend.core.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "")
    fallback = FakeLLM()
    svc = make_service(fallback)

    assert svc._llm_for(svc.persona_manager.get_persona("Architect")) is fallback


@pytest.mark.asyncio
async def test_dialog_is_interactive_for_budget():
    """Сообщение человека — интерактивный вызов, его бюджет не глушит (I-4)."""
    llm = RecordingLLM()
    svc = make_service(llm)

    await svc.handle("telegram", "42", "привет")
    await svc.drain()

    assert llm.kinds == ["interactive"]


# --- Скиллы из диалога (PR-6) ---


@pytest.fixture
def default_skills():
    from backend.services import skills as skills_svc

    skills_svc.create_default_skills()
    return skills_svc


@pytest.mark.asyncio
async def test_skill_trigger_executes_skill(default_skills):
    """DoD PR-6: триггер из диалога реально исполняет скилл."""
    from backend.services import tasks as task_svc

    llm = FakeLLM("модель не должна отвечать")
    svc = make_service(llm)

    reply = await svc.handle(
        "telegram", "42", "/skill publish-post topic=Запуск platform=telegram"
    )
    await svc.drain()

    assert "Publish Post" in reply
    # Скилл создаёт задачу — проверяем побочный эффект, а не только текст
    titles = [t.title for t in task_svc.list_tasks()]
    assert any("Запуск" in t for t in titles)
    # LLM в этом пути не звали — скилл не должен стоить денег
    assert llm.calls == []


@pytest.mark.asyncio
async def test_skill_params_are_passed_through(default_skills):
    from backend.services import tasks as task_svc

    svc = make_service()
    await svc.handle("telegram", "42", "/skill publish-post topic=Отчёт platform=x")
    await svc.drain()

    task = task_svc.list_tasks()[0]
    assert "Отчёт" in task.title
    assert "x" in task.description


@pytest.mark.asyncio
async def test_russian_skill_trigger_works(default_skills):
    svc = make_service()

    reply = await svc.handle("telegram", "42", "запусти скилл collect-metrics date=2026-08-11")
    await svc.drain()

    assert "Collect Metrics" in reply


@pytest.mark.asyncio
async def test_unknown_skill_lists_available(default_skills):
    svc = make_service()

    reply = await svc.handle("telegram", "42", "/skill выдуманный-скилл")
    await svc.drain()

    assert "не найден" in reply
    assert "publish-post" in reply


@pytest.mark.asyncio
async def test_skill_run_is_recorded_in_memory(default_skills):
    svc = make_service()

    await svc.handle("telegram", "42", "/skill collect-metrics date=2026-08-11")
    await svc.drain()

    facts = mem_svc.get_facts(layer=MemoryLayer.INBOX)
    assert len(facts) == 1
    assert "skill" in facts[0].tags


@pytest.mark.asyncio
async def test_normal_message_is_not_treated_as_skill(default_skills):
    """Слово «скилл» в обычной фразе не должно ничего запускать."""
    llm = FakeLLM("обычный ответ")
    svc = make_service(llm)

    reply = await svc.handle("telegram", "42", "расскажи, что такое скиллы в системе")
    await svc.drain()

    assert reply == "обычный ответ"
    assert len(llm.calls) == 1


# --- Извлечение сущностей в граф (PR-7) ---


class ExtractingLLM(FakeLLM):
    """Отвечает JSON-ом на промпт извлечения и обычным текстом на диалог."""

    def __init__(self):
        super().__init__("обычный ответ")
        self.background_calls = 0

    async def generate_response(
        self, user_message: str, context: str = "", kind: str = "interactive",
        json_mode: bool = False
    ) -> str:
        if kind == "background":
            self.background_calls += 1
            return (
                '{"entities": [{"name": "Одесса", "type": "concept"}],'
                ' "relations": []}'
            )
        return await super().generate_response(user_message, context, kind)


@pytest.mark.asyncio
async def test_dialog_fills_graph_in_background():
    """DoD PR-7: после диалога в графе появляются узлы."""
    from backend.services import graph as graph_svc

    svc = make_service(ExtractingLLM(), extract_entities=True)

    await svc.handle("telegram", "42", "я переезжаю в Одессу")
    await svc.drain()

    assert "Одесса" in [n.label for n in graph_svc.list_nodes()]


@pytest.mark.asyncio
async def test_reply_does_not_wait_for_extraction():
    """Латентность ответа не зависит от извлечения (I-5)."""
    from backend.services import graph as graph_svc

    svc = make_service(ExtractingLLM(), extract_entities=True)

    reply = await svc.handle("telegram", "42", "я переезжаю в Одессу")

    # Ответ уже у пользователя, граф ещё пуст
    assert reply == "обычный ответ"
    assert graph_svc.list_nodes() == []

    await svc.drain()


@pytest.mark.asyncio
async def test_extraction_can_be_switched_off():
    from backend.services import graph as graph_svc

    llm = ExtractingLLM()
    svc = make_service(llm, extract_entities=False)

    await svc.handle("telegram", "42", "я переезжаю в Одессу")
    await svc.drain()

    assert llm.background_calls == 0
    assert graph_svc.list_nodes() == []


@pytest.mark.asyncio
async def test_exhausted_budget_stops_extraction_but_not_dialog(monkeypatch):
    """Бюджет глушит фон, диалог продолжает работать (I-4)."""
    from backend.core.config import settings
    from backend.services import graph as graph_svc

    monkeypatch.setattr(settings, "daily_llm_budget_usd", 0.0)
    monkeypatch.setattr(budget_mod, "spent_today", lambda: 1.0)

    svc = make_service(ExtractingLLM(), extract_entities=True)

    reply = await svc.handle("telegram", "42", "я переезжаю в Одессу")
    await svc.drain()

    assert reply == "обычный ответ"
    assert graph_svc.list_nodes() == []


@pytest.mark.asyncio
async def test_extraction_failure_does_not_break_dialog(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("модель недоступна")

    monkeypatch.setattr(
        "backend.services.entity_extraction.extract_from_dialog", boom
    )
    svc = make_service(ExtractingLLM(), extract_entities=True)

    reply = await svc.handle("telegram", "42", "сообщение")
    await svc.drain()

    assert reply == "обычный ответ"


# --- Правки Пантеона влияют на следующее сообщение (PR-8) ---


@pytest.mark.asyncio
async def test_persona_model_change_affects_next_message(monkeypatch):
    """DoD PR-8: PUT персоны меняет реальное поведение следующего ответа."""
    from backend.services import personas as persona_store

    with_provider_keys(monkeypatch)
    svc = ConversationService(semantic_dedup=False, extract_entities=False)

    before = svc._llm_for(svc.persona_manager.get_persona("Architect"))
    assert before.model == svc.persona_manager.get_persona("Architect")["model"]

    persona_store.update_persona("Architect", {"model": "модель-из-теста"})

    after = svc._llm_for(svc.persona_manager.get_persona("Architect"))
    assert after.model == "модель-из-теста"
    assert after.model != before.model


@pytest.mark.asyncio
async def test_system_prompt_change_is_not_cached(monkeypatch):
    """Правка промпта не должна застревать в закэшированном клиенте."""
    from backend.services import personas as persona_store

    with_provider_keys(monkeypatch)
    svc = ConversationService(semantic_dedup=False, extract_entities=False)
    persona = svc.persona_manager.get_persona("Architect")

    persona_store.set_system_prompt("ПЕРВЫЙ ВАРИАНТ")
    assert "ПЕРВЫЙ ВАРИАНТ" in svc._llm_for(persona).system_prompt

    persona_store.set_system_prompt("ВТОРОЙ ВАРИАНТ")
    client = svc._llm_for(persona)
    assert "ВТОРОЙ ВАРИАНТ" in client.system_prompt
    assert "ПЕРВЫЙ ВАРИАНТ" not in client.system_prompt


@pytest.mark.asyncio
async def test_system_prompt_precedes_persona_prompt(monkeypatch):
    from backend.services import personas as persona_store

    with_provider_keys(monkeypatch)
    svc = ConversationService(semantic_dedup=False, extract_entities=False)
    persona_store.set_system_prompt("ОБЩЕЕ ПРАВИЛО")

    persona = svc.persona_manager.get_persona("Architect")
    prompt = svc._llm_for(persona).system_prompt

    # Ищем сам промпт персоны, а не её имя: развёрнутые промпты описывают
    # работу и слова «Architect» в себе не содержат
    assert prompt.index("ОБЩЕЕ ПРАВИЛО") < prompt.index(persona["system_prompt"])


@pytest.mark.asyncio
async def test_new_persona_can_be_used_immediately():
    """Без ключей провайдера — берётся подставной клиент, в сеть не ходим."""
    from backend.services import personas as persona_store

    persona_store.create_persona({
        "name": "Веста",
        "description": "тест",
        "model": "gpt-4-turbo",
        "provider": "openai",
        "system_prompt": "Ты Веста.",
    })
    llm = RecordingLLM()
    svc = ConversationService(llm=llm, semantic_dedup=False, extract_entities=False)

    await svc.handle("web", "42", "привет", persona="Веста")
    await svc.drain()

    assert "Веста" in llm.calls[0][1]


# --- Второй мозг: диалог читает память (PR-9) ---


class ContextCapturingLLM(FakeLLM):
    """Запоминает, какой контекст получил."""

    async def generate_response(
        self, user_message: str, context: str = "", kind: str = "interactive",
        json_mode: bool = False
    ) -> str:
        self.calls.append((user_message, context))
        return self.reply


def make_remembering_service(llm):
    return ConversationService(
        llm=llm, semantic_dedup=False, extract_entities=False, use_memory=True
    )


@pytest.mark.asyncio
async def test_known_facts_reach_the_model():
    """Ключевое: Hermes не только пишет в память, но и читает из неё."""
    mem_svc.add_fact("Nexus OS — личная операционная система фаундера", layer=MemoryLayer.CANON)
    llm = ContextCapturingLLM("ответ")
    svc = make_remembering_service(llm)

    await svc.handle("telegram", "42", "что такое Nexus OS?")
    await svc.drain()

    context = llm.calls[0][1]
    assert "личная операционная система" in context


@pytest.mark.asyncio
async def test_empty_memory_gives_clean_context():
    llm = ContextCapturingLLM("ответ")
    svc = make_remembering_service(llm)

    await svc.handle("telegram", "42", "первый вопрос вообще")
    await svc.drain()

    context = llm.calls[0][1]
    assert context.startswith("Persona:")
    assert "из памяти" not in context


@pytest.mark.asyncio
async def test_memory_can_be_switched_off():
    mem_svc.add_fact("секретный факт про Одессу", layer=MemoryLayer.CANON)
    llm = ContextCapturingLLM("ответ")
    svc = ConversationService(
        llm=llm, semantic_dedup=False, extract_entities=False, use_memory=False
    )

    await svc.handle("telegram", "42", "расскажи про Одессу")
    await svc.drain()

    assert "секретный факт" not in llm.calls[0][1]


@pytest.mark.asyncio
async def test_broken_recall_does_not_break_dialog(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("векторный стор недоступен")

    monkeypatch.setattr(mem_svc, "recall", boom)
    llm = ContextCapturingLLM("ответ несмотря ни на что")
    svc = make_remembering_service(llm)

    reply = await svc.handle("telegram", "42", "вопрос")
    await svc.drain()

    assert reply == "ответ несмотря ни на что"


# --- Нить разговора: короткая память диалога (PR-16) ---


@pytest.mark.asyncio
async def test_previous_turn_reaches_the_model():
    """Ключевое: второе сообщение видит первое — диалог перестал быть одиночным."""
    llm = ContextCapturingLLM("хорошо")
    svc = make_service(llm)

    await svc.handle("telegram", "42", "меня зовут Вадим")
    await svc.drain()
    await svc.handle("telegram", "42", "как меня зовут?")
    await svc.drain()

    context = llm.calls[1][1]
    assert "меня зовут Вадим" in context
    assert "хорошо" in context


@pytest.mark.asyncio
async def test_first_message_has_no_thread():
    llm = ContextCapturingLLM("ответ")
    svc = make_service(llm)

    await svc.handle("telegram", "42", "первое сообщение")
    await svc.drain()

    assert "Недавняя переписка" not in llm.calls[0][1]


@pytest.mark.asyncio
async def test_thread_does_not_leak_between_channels():
    llm = ContextCapturingLLM("ответ")
    svc = make_service(llm)

    await svc.handle("telegram", "42", "сказано в телеграме")
    await svc.drain()
    await svc.handle("web", "42", "вопрос с сайта")
    await svc.drain()

    assert "сказано в телеграме" not in llm.calls[1][1]


@pytest.mark.asyncio
async def test_history_can_be_switched_off():
    llm = ContextCapturingLLM("ответ")
    svc = ConversationService(
        llm=llm, semantic_dedup=False, extract_entities=False, use_history=False
    )

    await svc.handle("telegram", "42", "первое")
    await svc.drain()
    await svc.handle("telegram", "42", "второе")
    await svc.drain()

    assert "первое" not in llm.calls[1][1]


@pytest.mark.asyncio
async def test_thread_is_written_before_reply_returns():
    """История обязана лечь до возврата ответа: следующее сообщение может
    прийти сразу, и фоновая запись за ним не успеет."""
    from backend.services import dialog_history

    svc = make_service(FakeLLM("ответ"))

    await svc.handle("telegram", "42", "вопрос")

    assert len(dialog_history.recent("telegram", "42")) == 2
    await svc.drain()


@pytest.mark.asyncio
async def test_broken_history_does_not_break_dialog(monkeypatch):
    from backend.services import dialog_history

    def boom(*args, **kwargs):
        raise RuntimeError("файл истории недоступен")

    monkeypatch.setattr(dialog_history, "append_turn", boom)
    monkeypatch.setattr(dialog_history, "render", boom)
    svc = make_service(FakeLLM("ответ несмотря ни на что"))

    reply = await svc.handle("telegram", "42", "вопрос")
    await svc.drain()

    assert reply == "ответ несмотря ни на что"


@pytest.mark.asyncio
async def test_skill_run_stays_in_the_thread(default_skills):
    """Запуск скилла — тоже часть разговора: «а что я сейчас запускал» не слепнет."""
    from backend.services import dialog_history

    svc = make_service()

    await svc.handle("telegram", "42", "/skill collect-metrics date=2026-08-11")
    await svc.drain()

    thread = dialog_history.render("telegram", "42")
    assert "collect-metrics" in thread
    assert "Skill" in thread


# --- Критик: только для Сехмет и Philosopher (Имхотепа), см. critic.py ---


@pytest.mark.asyncio
async def test_critic_leaves_a_passing_reply_untouched():
    llm = FakeLLM("черновик Сехмет")
    llm.chat_reply = "PASS. Находка обоснована."
    svc = make_service(llm)

    reply = await svc.handle("web", "42", "что случилось", persona="Sekhmet")
    await svc.drain()

    assert reply == "черновик Сехмет"
    assert len(llm.chat_calls) == 1


@pytest.mark.asyncio
async def test_critic_revision_replaces_the_final_reply():
    llm = FakeLLM("черновик Имхотепа")
    svc = make_service(llm)

    # Первый chat() — вердикт критика, второй — правка самой персоны
    calls = iter(["NEEDS REVISION: не назвал цену отката.", "поправленный ответ Имхотепа"])

    async def fake_chat(messages, **kwargs):
        from backend.services.llm import LLMResponse

        return LLMResponse(content=next(calls), model="fake")

    llm.chat = fake_chat

    reply = await svc.handle("web", "42", "стоит ли переезжать на новую БД", persona="Philosopher")
    await svc.drain()

    assert reply == "поправленный ответ Имхотепа"


@pytest.mark.asyncio
async def test_architect_gets_advisor_not_critic():
    llm = FakeLLM("обычный ответ")
    svc = make_service(llm)

    await svc.handle("web", "42", "напиши код", persona="Architect")
    await svc.drain()

    # Советчик всё-таки зовётся (Птах его получил), но по умолчанию PASS
    # у FakeLLM не годится как "совет" — реальный текст задаётся отдельно
    assert len(llm.chat_calls) == 1


@pytest.mark.asyncio
async def test_advisor_suggestion_is_appended_to_the_reply():
    llm = FakeLLM("черновик Птаха")
    llm.chat_reply = "Проще взять готовую библиотеку вместо своего парсера."
    svc = make_service(llm)

    reply = await svc.handle("web", "42", "напиши код", persona="Architect")
    await svc.drain()

    assert reply == "черновик Птаха\n\n— Совет: Проще взять готовую библиотеку вместо своего парсера."


@pytest.mark.asyncio
async def test_no_addition_leaves_the_reply_untouched():
    llm = FakeLLM("черновик Птаха")
    llm.chat_reply = "no addition"
    svc = make_service(llm)

    reply = await svc.handle("web", "42", "напиши код", persona="Architect")
    await svc.drain()

    assert reply == "черновик Птаха"


@pytest.mark.asyncio
async def test_other_personas_never_call_the_critic_or_advisor():
    llm = FakeLLM("обычный ответ")
    svc = make_service(llm)

    await svc.handle("web", "42", "что угодно", persona="Bastet")
    await svc.drain()

    assert llm.chat_calls == []
