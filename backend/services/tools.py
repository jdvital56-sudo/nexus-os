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
from typing import Any, Callable, Awaitable

import httpx

from . import budget, computer_use, websearch
from .llm import LLMMessage, LLMResponse, LLMService

logger = logging.getLogger(__name__)

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
}

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
