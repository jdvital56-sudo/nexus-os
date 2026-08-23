"""Цикл вызова инструментов: модель просит — мы выполняем — модель отвечает.

Почему отдельный файл, а не правка `llm.py`. У `LLMService.chat()` нет и не
было tool-calling: ни одна персона не могла ничего вызвать, «веб-исследование»
у Сешат жило только словами в промпте. Добавлять цикл прямо в `chat()` сейчас
нельзя — файл одновременно правит соседняя линия работ, и мы бы столкнулись.
Здесь тот же протокол OpenAI/DeepSeek, но своим запросом; когда `llm.py`
освободится, это переезжает внутрь одним движением.

Инструменты доступны не всем персонам: лишний вызов стоит денег и времени,
а большинству персон в вебе делать нечего.
"""
import json
import logging
from typing import Any, AsyncGenerator, Callable, Awaitable

import httpx

from . import budget, computer_use, tts, websearch
from .llm import LLMMessage, LLMResponse, LLMService

logger = logging.getLogger(__name__)

# 23.08.2026: фаундер спросил Ра голосом, где и как подключён её голос — она
# честно не знала и начала расспрашивать его самого (её единственные
# источники — recall() по прошлым разговорам и заметки Obsidian, а там про
# TTS/wakeword ни слова, проверено). У неё не было способа посмотреть в
# конфиг сама. Этот инструмент даёт ей такой способ — не гадать и не
# переспрашивать то, что физически лежит в .env этой же машины.
SYSTEM_STATUS_SPEC = {
    "type": "function",
    "function": {
        "name": "system_status",
        "description": (
            "Текущая техническая конфигурация Nexus OS: какой движок и "
            "голос синтеза речи (TTS) сейчас включён, готов ли он к работе, "
            "и как устроено пробуждение по имени «Джарвис». Зови это вместо "
            "вопроса фаундеру «где именно вы это подключали» — можно "
            "посмотреть самой."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


async def run_system_status(_arguments: dict, _action_key: str = "") -> str:
    s = tts.status()
    lines = [
        f"TTS-движок: {s['engine']} ({s['detail']})",
        f"Готов к синтезу: {'да' if s['ready'] else 'нет'}",
        f"Текущий голос: {s['voice']}",
        "Пробуждение по имени «Джарвис»: браузер — встроенное распознавание "
        "речи Chrome/Edge; плавающий виджет (Electron) — локальный офлайн-"
        "сервер wakeword/server.py на Vosk, слушает порт 127.0.0.1:8422, "
        "запускается вручную через wakeword/start.ps1.",
    ]
    return "\n".join(lines)

# Сколько раз подряд модель может позвать инструмент, прежде чем мы прервём.
# Без предела модель, не найдя ответа, ищет по кругу и тратит деньги.
MAX_ROUNDS = 3

REQUEST_TIMEOUT = 90.0

# Кто имеет право ходить в веб. Ключи — как в personas.json (регистр не важен).
# Ра отвечает на большинство вопросов, поэтому поиск ему нужен; Сешат — это
# её прямая работа; Бастет проверяет клиентов и рынок. Остальным незачем:
# код и глубокий разбор от веба не выигрывают, а платить пришлось бы за всех.
WEB_SEARCH_PERSONAS = {"orpheus", "labyrinth", "bastet"}

# Кто имеет право трогать мышь и клавиатуру фаундера (шаг 3, 19.08.2026).
# Только Ра/Orpheus — общий голос, с которым он и просил это делать.
# Персонам вроде Птаха (код) или Сехмет (безопасность) клик по экрану не
# нужен для их работы, а держать список коротким — держать риск ниже.
COMPUTER_USE_PERSONAS = {"orpheus"}

# Реестр инструментов: описание для модели + чем исполнять
_REGISTRY: dict[str, tuple[dict[str, Any], Callable[[dict], Awaitable[str]]]] = {
    "web_search": (websearch.TOOL_SPEC, websearch.run_tool),
    "screen_look": (computer_use.SCREEN_LOOK_SPEC, computer_use.run_screen_look),
    "screen_click": (computer_use.SCREEN_CLICK_SPEC, computer_use.run_screen_click),
    "screen_type": (computer_use.SCREEN_TYPE_SPEC, computer_use.run_screen_type),
    "screen_key": (computer_use.SCREEN_KEY_SPEC, computer_use.run_screen_key),
    "screen_scroll": (computer_use.SCREEN_SCROLL_SPEC, computer_use.run_screen_scroll),
    "system_status": (SYSTEM_STATUS_SPEC, run_system_status),
}

# Кто может спросить систему о её же настройках (голос, wakeword). Только
# Ра — тот же круг, что и computer_use ниже: он общий голос, ему и задают
# вопросы вида «как ты сейчас настроена».
SYSTEM_STATUS_PERSONAS = {"orpheus"}

_COMPUTER_USE_TOOLS = ["screen_look", "screen_click", "screen_type", "screen_key", "screen_scroll"]


def tools_for(persona_name: str) -> list[dict[str, Any]]:
    """Инструменты, доступные персоне. Пустой список — обычный вызов без них."""
    name = (persona_name or "").strip().lower()
    tools: list[dict[str, Any]] = []
    if name in WEB_SEARCH_PERSONAS and websearch.is_configured():
        tools.append(_REGISTRY["web_search"][0])
    # Без ключа Gemini screen_look гарантированно откажет, а без него
    # координаты для click/type взять неоткуда — тот же принцип, что у
    # web_search выше: не предлагать модели инструмент, который заведомо
    # не сработает (найдено код-ревью 19.08.2026).
    if name in COMPUTER_USE_PERSONAS and computer_use.vision_configured():
        tools.extend(_REGISTRY[key][0] for key in _COMPUTER_USE_TOOLS)
    if name in SYSTEM_STATUS_PERSONAS:
        tools.append(_REGISTRY["system_status"][0])
    return tools


def supports_tools(llm: LLMService) -> bool:
    """Публичная — вызывающая сторона (`conversation.py`) должна проверить
    ДО того, как решать, идти ли через `chat_with_tools` вообще: запасной
    путь внутри неё дёргает `llm.chat()`, а не `llm.generate_response()`,
    который только и знают тестовые дублёры LLM. Если сюда дойти с
    дублёром, всё равно упадёт — просто на шаг позже и с менее понятной
    ошибкой."""
    # Anthropic говорит на своём формате инструментов, Gemini и Ollama — на
    # третьем. Пока поддерживаем только OpenAI-совместимых, чтобы не делать
    # три ветки ради функции, которой ещё никто не пользовался.
    #
    # getattr, а не llm.provider: у тестовых дублёров LLM этого поля нет
    # вовсе, и у них нет своего tool-calling — тот же случай, что и
    # Anthropic/Gemini, а не повод падать.
    return getattr(llm, "provider", None) in ("openai", "deepseek")


async def _execute(name: str, raw_arguments: str, action_key: str = "") -> str:
    entry = _REGISTRY.get(name)
    if entry is None:
        return f"Инструмент «{name}» не существует."
    try:
        arguments = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError:
        # Модель иногда присылает почти-JSON. Молча подставлять пустой запрос
        # нельзя — получится поиск не того, о чём просили.
        return f"Не разобрал аргументы вызова: {raw_arguments!r}"
    if not isinstance(arguments, dict):
        return f"Аргументы должны быть объектом, пришло: {type(arguments).__name__}"
    # action_key («channel:user_id») нужен только screen_click/screen_type —
    # чтобы знать, кому класть заблокированное действие в pending_action.py.
    # Остальные инструменты его игнорируют, но принимают, чтобы регистр
    # оставался единым и не ветвился по типу инструмента здесь.
    return await entry[1](arguments, action_key)


async def chat_with_tools(
    llm: LLMService,
    messages: list[LLMMessage],
    tools: list[dict[str, Any]],
    temperature: float = 0.7,
    max_tokens: int = 2000,
    kind: str = "interactive",
    action_key: str = "",
) -> LLMResponse:
    """Как `llm.chat()`, но модель может позвать инструмент.

    Без инструментов или на провайдере без их поддержки просто уходит в
    обычный `chat()` — вызывающему не нужно об этом думать.
    """
    if not tools or not supports_tools(llm):
        return await llm.chat(messages, temperature=temperature, max_tokens=max_tokens, kind=kind)

    within_budget = budget.check(kind)

    url = f"{llm.base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {llm.api_key}",
        "Content-Type": "application/json",
    }

    # Своя копия истории: дописываем ответы модели и результаты инструментов,
    # чтобы у неё был полный ход разговора при следующем круге
    history: list[dict[str, Any]] = [m.to_dict() for m in messages]
    if llm.system_prompt and not any(m.get("role") == "system" for m in history):
        history.insert(0, {"role": "system", "content": llm.system_prompt})

    used_tools: list[str] = []
    total_usage: dict[str, int] = {}

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for round_number in range(MAX_ROUNDS + 1):
            # На последнем круге инструменты убираем: модель обязана ответить
            # словами, а не просить ещё один поиск
            offer_tools = round_number < MAX_ROUNDS
            payload: dict[str, Any] = {
                "model": llm.model,
                "messages": history,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if offer_tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            usage = data.get("usage") or {}
            for key, value in usage.items():
                if isinstance(value, int):
                    total_usage[key] = total_usage.get(key, 0) + value

            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            calls = message.get("tool_calls") or []

            if not calls:
                content = message.get("content") or ""
                cost = budget.record(llm.model, total_usage)
                if cost:
                    total_usage["cost_usd"] = round(cost, 6)
                if used_tools:
                    total_usage["tools_used"] = len(used_tools)
                    logger.info("Инструменты за ответ: %s", ", ".join(used_tools))
                result = LLMResponse(content=content, model=llm.model, usage=total_usage)
                result.over_budget = not within_budget
                return result

            # Ответ модели с просьбой о вызове обязан остаться в истории:
            # без него следующий запрос отвергается — результат ссылается на
            # вызов, которого в разговоре нет
            history.append(message)

            for call in calls:
                function = call.get("function") or {}
                name = function.get("name") or ""
                used_tools.append(name)
                output = await _execute(name, function.get("arguments") or "{}", action_key)
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": output,
                    }
                )

    # Сюда попадаем, только если модель на каждом круге просила инструмент
    logger.warning("Модель не уложилась в %d обращений к инструментам", MAX_ROUNDS)
    result = LLMResponse(
        content="Не удалось собрать ответ: слишком много обращений к поиску.",
        model=llm.model,
        usage=total_usage,
    )
    result.over_budget = not within_budget
    return result


# === Потоковый путь ===
#
# 23.08.2026: фаундер пожаловался вживую — «отвечает, но очень медленно,
# большая задержка». Причина не в самой модели (~1.8с), а в том, что весь
# конвейер ждал ПОЛНЫЙ текст ответа, прежде чем хоть что-то показать или
# озвучить, — на длинном ответе это несколько секунд тишины впустую.
# Раунды с реальным вызовом инструмента всё равно нельзя ни исполнить, ни
# озвучить частично: там ждём целиком, как и раньше. Но финальный раунд
# (тот, что реально произносится вслух) отдаёт текст по мере генерации.


async def _iter_sse_events(
    client: httpx.AsyncClient, url: str, headers: dict, payload: dict
) -> AsyncGenerator[tuple[str, Any], None]:
    """Разбирает SSE-поток одного раунда OpenAI-совместимого API.

    Отдаёт ("content", кусок_текста) по мере прихода и, если раунд решил
    вызвать инструмент — ("tool_calls", список) в конце: id/имя/аргументы
    приходят кусками по индексу, здесь они уже склеены в тот же вид, что и
    в обычном (нестримовом) ответе, дальше по коду разницы нет.
    """
    calls: dict[int, dict] = {}
    usage: dict[str, int] = {}
    async with client.stream("POST", url, headers=headers, json={**payload, "stream": True}) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[len("data:"):].strip()
            if raw == "[DONE]":
                break
            data = json.loads(raw)
            if data.get("usage"):
                usage = data["usage"]
            choice = (data.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            if delta.get("content"):
                yield ("content", delta["content"])
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                slot = calls.setdefault(
                    idx, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                )
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["function"]["name"] += fn["name"]
                if fn.get("arguments"):
                    slot["function"]["arguments"] += fn["arguments"]
    if calls:
        yield ("tool_calls", [calls[i] for i in sorted(calls)])
    if usage:
        yield ("usage", usage)


async def _plain_stream(
    llm: LLMService, messages: list[LLMMessage], temperature: float, max_tokens: int, kind: str
) -> AsyncGenerator[str, None]:
    """Стриминг без инструментов вообще — персоне они не положены."""
    # Возврат не проверяем: у потокового ответа нет LLMResponse, чтобы
    # выставить over_budget — check() всё равно нужен ради своего побочного
    # эффекта (BudgetExceeded для kind=background, событие в Activity).
    budget.check(kind)
    url = f"{llm.base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {llm.api_key}", "Content-Type": "application/json"}
    history: list[dict[str, Any]] = [m.to_dict() for m in messages]
    if llm.system_prompt and not any(m.get("role") == "system" for m in history):
        history.insert(0, {"role": "system", "content": llm.system_prompt})
    payload = {"model": llm.model, "messages": history, "temperature": temperature, "max_tokens": max_tokens}

    total_usage: dict[str, int] = {}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        async for kind_, value in _iter_sse_events(client, url, headers, payload):
            if kind_ == "content":
                yield value
            elif kind_ == "usage":
                for k, v in value.items():
                    if isinstance(v, int):
                        total_usage[k] = total_usage.get(k, 0) + v
    budget.record(llm.model, total_usage)


async def chat_with_tools_stream(
    llm: LLMService,
    messages: list[LLMMessage],
    tools: list[dict[str, Any]],
    temperature: float = 0.7,
    max_tokens: int = 2000,
    kind: str = "interactive",
    action_key: str = "",
) -> AsyncGenerator[str, None]:
    """Как `chat_with_tools`, но финальный ответ отдаёт кусками по мере
    генерации, а не одним блоком в конце. Раунды, где модель зовёт
    инструмент, всё равно собираются целиком — частично пришедший вызов
    ни исполнить, ни озвучить нельзя; в потоке они просто не производят
    текста, который стоило бы отдавать наружу (проверено на практике
    DeepSeek/OpenAI: раунд с tool_calls не шлёт content одновременно)."""
    if not tools or not supports_tools(llm):
        async for delta in _plain_stream(llm, messages, temperature, max_tokens, kind):
            yield delta
        return

    # См. комментарий в _plain_stream выше — тот же резон.
    budget.check(kind)
    url = f"{llm.base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {llm.api_key}", "Content-Type": "application/json"}
    history: list[dict[str, Any]] = [m.to_dict() for m in messages]
    if llm.system_prompt and not any(m.get("role") == "system" for m in history):
        history.insert(0, {"role": "system", "content": llm.system_prompt})

    total_usage: dict[str, int] = {}

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for round_number in range(MAX_ROUNDS + 1):
            offer_tools = round_number < MAX_ROUNDS
            payload: dict[str, Any] = {
                "model": llm.model,
                "messages": history,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if offer_tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            tool_calls_this_round: list[dict] | None = None
            content_parts: list[str] = []
            async for kind_, value in _iter_sse_events(client, url, headers, payload):
                if kind_ == "content":
                    content_parts.append(value)
                    yield value
                elif kind_ == "tool_calls":
                    tool_calls_this_round = value
                elif kind_ == "usage":
                    for k, v in value.items():
                        if isinstance(v, int):
                            total_usage[k] = total_usage.get(k, 0) + v

            if not tool_calls_this_round:
                budget.record(llm.model, total_usage)
                return

            history.append(
                {"role": "assistant", "content": "".join(content_parts) or None, "tool_calls": tool_calls_this_round}
            )
            for call in tool_calls_this_round:
                function = call.get("function") or {}
                name = function.get("name") or ""
                output = await _execute(name, function.get("arguments") or "{}", action_key)
                history.append(
                    {"role": "tool", "tool_call_id": call.get("id"), "content": output}
                )

    logger.warning("Модель не уложилась в %d обращений к инструментам (поток)", MAX_ROUNDS)
    yield "Не удалось собрать ответ: слишком много обращений к поиску."
