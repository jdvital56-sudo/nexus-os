"""Веб-поиск и цикл вызова инструментов.

Живьём в Firecrawl не ходим: это деньги и сеть в тестах. Проверяем разбор
ответа, поведение при поломках и то, что модель действительно получает
результат инструмента обратно.
"""
import json

import httpx
import pytest

from backend.core.config import settings
from backend.services import tools as tools_svc
from backend.services import websearch
from backend.services.llm import LLMMessage, LLMService


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(settings, "firecrawl_api_key", "fc-test-key")


@pytest.fixture
def without_key(monkeypatch):
    monkeypatch.setattr(settings, "firecrawl_api_key", "")


# --- Поиск ---


def test_is_configured_follows_the_key(with_key):
    assert websearch.is_configured()


@pytest.mark.asyncio
async def test_search_without_key_says_so(without_key):
    with pytest.raises(websearch.SearchUnavailable) as e:
        await websearch.search("что угодно")
    assert "FIRECRAWL_API_KEY" in str(e.value)


@pytest.mark.asyncio
async def test_empty_query_is_an_error_not_empty_result(with_key):
    """Пустой список неотличим от поломки — поэтому исключение."""
    with pytest.raises(websearch.SearchUnavailable):
        await websearch.search("   ")


def test_parse_skips_results_without_url():
    """Без ссылки результат непроверяем: человек не может его подтвердить."""
    parsed = websearch._parse(
        {
            "data": [
                {"title": "Есть ссылка", "url": "https://a.example", "markdown": "текст"},
                {"title": "Нет ссылки", "markdown": "текст"},
                {"title": "Пустая ссылка", "url": "  ", "markdown": "текст"},
            ]
        }
    )
    assert [r.url for r in parsed] == ["https://a.example"]


def test_parse_falls_back_to_description_then_url():
    parsed = websearch._parse(
        {"data": [{"url": "https://b.example", "description": "краткое"}]}
    )
    assert parsed[0].snippet == "краткое"
    assert parsed[0].title == "https://b.example"


def test_snippet_is_clipped_on_a_word_boundary():
    """Обрывок посреди слова модель достраивает сама и выдаёт за цитату."""
    long_text = ("слово " * 5000).strip()
    clipped = websearch._clip(long_text)
    assert len(clipped) <= websearch.SNIPPET_CHARS + 1
    assert clipped.endswith("…")
    assert not clipped[:-1].endswith("сло")


def test_short_snippet_is_left_alone():
    assert websearch._clip("  коротко  ") == "коротко"


@pytest.mark.asyncio
async def test_bad_key_is_reported_plainly(with_key, monkeypatch):
    async def fake_post(self, url, **kwargs):
        return httpx.Response(401, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(websearch.SearchUnavailable) as e:
        await websearch.search("запрос")
    assert "ключ" in str(e.value).lower()


@pytest.mark.asyncio
async def test_rate_limit_is_reported_plainly(with_key, monkeypatch):
    async def fake_post(self, url, **kwargs):
        return httpx.Response(429, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(websearch.SearchUnavailable) as e:
        await websearch.search("запрос")
    assert "лимит" in str(e.value).lower()


@pytest.mark.asyncio
async def test_limit_is_clamped(with_key, monkeypatch):
    seen = {}

    async def fake_post(self, url, **kwargs):
        seen.update(kwargs.get("json") or {})
        return httpx.Response(200, json={"data": []}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    await websearch.search("запрос", limit=999)
    assert seen["limit"] == websearch.MAX_LIMIT


# --- Инструмент для модели ---


@pytest.mark.asyncio
async def test_run_tool_returns_failure_as_text(without_key):
    """Модель должна узнать о поломке и сказать человеку, а не отвечать по памяти."""
    out = await websearch.run_tool({"query": "что-нибудь"})
    assert "ПОИСК НЕ УДАЛСЯ" in out
    assert "не выдумывай" in out


@pytest.mark.asyncio
async def test_run_tool_formats_results_with_links(with_key, monkeypatch):
    async def fake_post(self, url, **kwargs):
        return httpx.Response(
            200,
            json={"data": [{"title": "Заголовок", "url": "https://x.example", "markdown": "суть"}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    out = await websearch.run_tool({"query": "запрос"})
    assert "https://x.example" in out
    assert "Заголовок" in out


@pytest.mark.asyncio
async def test_run_tool_says_when_nothing_found(with_key, monkeypatch):
    async def fake_post(self, url, **kwargs):
        return httpx.Response(200, json={"data": []}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    out = await websearch.run_tool({"query": "запрос"})
    assert "Ничего не найдено" in out


# --- Кому доступен поиск ---


def test_only_listed_personas_get_the_tool(with_key):
    assert tools_svc.tools_for("Orpheus")
    assert tools_svc.tools_for("labyrinth")  # регистр не важен
    assert tools_svc.tools_for("Bastet")
    assert tools_svc.tools_for("Architect") == []
    assert tools_svc.tools_for("Philosopher") == []


def test_no_tool_without_a_key(without_key, monkeypatch):
    """Предлагать модели инструмент, который заведомо не сработает, — обман.

    Найдено код-ревью 19.08.2026: этот тест раньше проверял ровно пустой
    список у Орфея без ключа — после появления инструментов экрана
    (шаг 3, свой отдельный ключ GEMINI_API_KEY, от Firecrawl не зависит)
    первая правка ослабила проверку до «просто нет web_search», потеряв
    гарантию точного списка. Здесь оба ключа сведены явно, чтобы список
    снова был проверяемым целиком, а не только одним пунктом.

    23.08.2026: system_status не зависит ни от одного ключа (читает только
    .env этой же машины) — он остаётся, даже когда все внешние инструменты
    заведомо не сработают и убраны."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert tools_svc.tools_for("Orpheus") == [tools_svc.SYSTEM_STATUS_SPEC]

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    names = [t["function"]["name"] for t in tools_svc.tools_for("Orpheus")]
    assert "web_search" not in names
    assert "screen_click" in names  # свой ключ, не зависит от Firecrawl


def test_unknown_persona_gets_nothing(with_key):
    assert tools_svc.tools_for("Кто-то новый") == []
    assert tools_svc.tools_for("") == []


# --- Цикл вызова ---


def _llm() -> LLMService:
    return LLMService(
        provider="deepseek",
        model="deepseek-chat",
        api_key="sk-test",
        base_url="https://api.deepseek.test/v1",
        system_prompt="ОБЩЕЕ ПРАВИЛО",
    )


@pytest.mark.asyncio
async def test_without_tools_falls_back_to_plain_chat(monkeypatch):
    called = {}

    async def fake_chat(self, messages, **kwargs):
        called["yes"] = True
        from backend.services.llm import LLMResponse

        return LLMResponse(content="обычный ответ", model=self.model, usage={})

    monkeypatch.setattr(LLMService, "chat", fake_chat)
    result = await tools_svc.chat_with_tools(_llm(), [LLMMessage("user", "привет")], tools=[])
    assert called.get("yes")
    assert result.content == "обычный ответ"


@pytest.mark.asyncio
async def test_anthropic_falls_back_too(monkeypatch):
    """У Anthropic свой формат инструментов — не притворяемся, что умеем."""
    async def fake_chat(self, messages, **kwargs):
        from backend.services.llm import LLMResponse

        return LLMResponse(content="ответ", model=self.model, usage={})

    monkeypatch.setattr(LLMService, "chat", fake_chat)
    llm = LLMService(provider="anthropic", model="m", api_key="k", base_url="https://x")
    result = await tools_svc.chat_with_tools(
        llm, [LLMMessage("user", "привет")], tools=[websearch.TOOL_SPEC]
    )
    assert result.content == "ответ"


@pytest.mark.asyncio
async def test_tool_result_goes_back_to_the_model(with_key, monkeypatch):
    """Главное в цикле: модель просит поиск, получает результат и отвечает по нему."""
    rounds = []

    async def fake_post(self, url, **kwargs):
        payload = kwargs.get("json") or {}
        rounds.append(payload)
        if len(rounds) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {
                                            "name": "web_search",
                                            "arguments": json.dumps({"query": "курс"}),
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Нашёл: 42"}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 7},
            },
            request=httpx.Request("POST", url),
        )

    async def fake_tool(arguments, action_key=""):
        return "[1] Ответ\nhttps://z.example\n42"

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setitem(tools_svc._REGISTRY, "web_search", (websearch.TOOL_SPEC, fake_tool))

    result = await tools_svc.chat_with_tools(
        _llm(), [LLMMessage("user", "какой курс?")], tools=[websearch.TOOL_SPEC]
    )

    assert result.content == "Нашёл: 42"
    # Второй запрос обязан нести и просьбу модели, и результат инструмента
    second = rounds[1]["messages"]
    assert any(m.get("role") == "tool" and "42" in m.get("content", "") for m in second)
    assert any(m.get("tool_calls") for m in second)
    # Расход посчитан по обоим запросам, а не по последнему
    assert result.usage["prompt_tokens"] == 30
    assert result.usage["tools_used"] == 1


@pytest.mark.asyncio
async def test_system_prompt_is_added_once(with_key, monkeypatch):
    seen = []

    async def fake_post(self, url, **kwargs):
        seen.append(kwargs["json"]["messages"])
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ок"}}], "usage": {}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    await tools_svc.chat_with_tools(
        _llm(), [LLMMessage("user", "привет")], tools=[websearch.TOOL_SPEC]
    )
    systems = [m for m in seen[0] if m.get("role") == "system"]
    assert len(systems) == 1
    assert systems[0]["content"] == "ОБЩЕЕ ПРАВИЛО"


@pytest.mark.asyncio
async def test_endless_tool_calls_are_cut_off(with_key, monkeypatch):
    """Модель, не находя ответа, ищет по кругу и тратит деньги."""
    calls = {"n": 0}

    async def fake_post(self, url, **kwargs):
        calls["n"] += 1
        has_tools = "tools" in (kwargs.get("json") or {})
        if has_tools:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "id": f"c{calls['n']}",
                                        "function": {"name": "web_search", "arguments": "{}"},
                                    }
                                ]
                            }
                        }
                    ],
                    "usage": {},
                },
                request=httpx.Request("POST", url),
            )
        # На последнем круге инструменты не предложены — модель обязана ответить
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "сдаюсь"}}], "usage": {}},
            request=httpx.Request("POST", url),
        )

    async def fake_tool(arguments, action_key=""):
        return "ничего"

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setitem(tools_svc._REGISTRY, "web_search", (websearch.TOOL_SPEC, fake_tool))

    result = await tools_svc.chat_with_tools(
        _llm(), [LLMMessage("user", "?")], tools=[websearch.TOOL_SPEC]
    )
    assert result.content == "сдаюсь"
    assert calls["n"] == tools_svc.MAX_ROUNDS + 1


@pytest.mark.asyncio
async def test_broken_arguments_do_not_crash_the_dialog(with_key):
    out = await tools_svc._execute("web_search", "{это не json}")
    assert "Не разобрал аргументы" in out


@pytest.mark.asyncio
async def test_unknown_tool_is_reported(with_key):
    out = await tools_svc._execute("выдуманный", "{}")
    assert "не существует" in out
