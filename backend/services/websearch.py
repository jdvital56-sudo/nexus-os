"""Живой веб-поиск через Firecrawl.

Зачем. До этого система знала только то, что помнила модель: ключ
`FIRECRAWL_API_KEY` читался в конфиге, но ни одного запроса к Firecrawl в
коде не было. Персона Сешат («исследование и веб-поиск») описывала поиск
словами в промпте, а сходить никуда не могла.

Здесь ровно два слоя и ничего больше: `search()` — один HTTP-запрос, и
`TOOL_SPEC` — описание того же самого для модели. Разбор ответа модели и
цикл вызовов живут в `tools.py`, чтобы этот файл можно было проверить
отдельно, не поднимая модель.
"""
import asyncio
import logging
from typing import Any

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)

API_URL = "https://api.firecrawl.dev/v1/search"

# Дольше ждать нет смысла: пользователь сидит и смотрит в экран, а поиск
# нужен как подсказка к ответу, а не как самостоятельная ценность.
TIMEOUT_SECONDS = 20.0

# Пять результатов — предел, после которого модель начинает пересказывать
# выдачу вместо ответа. Проверять на глаз, не увеличивать «на всякий случай».
DEFAULT_LIMIT = 5
MAX_LIMIT = 10

# Обрезка выдержки. Firecrawl возвращает страницу целиком; целиком она
# съедает контекст и деньги, а для ответа хватает начала.
SNIPPET_CHARS = 1200


class SearchUnavailable(RuntimeError):
    """Поиск не настроен или не ответил. Текст показываем человеку как есть."""


class SearchResult:
    __slots__ = ("title", "url", "snippet")

    def __init__(self, title: str, url: str, snippet: str) -> None:
        self.title = title
        self.url = url
        self.snippet = snippet

    def to_dict(self) -> dict[str, str]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}

    def __repr__(self) -> str:  # для отладки в логах
        return f"SearchResult({self.url!r})"


def is_configured() -> bool:
    """Есть ли ключ. Отдельной функцией — чтобы экраны могли честно сказать,
    что поиск выключен, вместо того чтобы падать на первом запросе."""
    return bool(settings.firecrawl_api_key)


def _clip(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= SNIPPET_CHARS:
        return text
    # Режем по границе слова: обрывок посреди слова модель иногда достраивает
    # сама и выдаёт выдуманное окончание за цитату
    cut = text[:SNIPPET_CHARS].rsplit(" ", 1)[0]
    return cut + "…"


def _parse(payload: dict[str, Any]) -> list[SearchResult]:
    out: list[SearchResult] = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url:
            continue  # без ссылки результат непроверяем, а значит бесполезен
        snippet = item.get("markdown") or item.get("description") or ""
        out.append(
            SearchResult(
                title=(item.get("title") or url).strip(),
                url=url,
                snippet=_clip(snippet),
            )
        )
    return out


async def search(query: str, limit: int = DEFAULT_LIMIT) -> list[SearchResult]:
    """Ищет в вебе. Пустой запрос и отсутствие ключа — ошибка, не пустой список:
    молчаливое «ничего не нашлось» неотличимо от поломки."""
    query = (query or "").strip()
    if not query:
        raise SearchUnavailable("Пустой поисковый запрос")
    if not is_configured():
        raise SearchUnavailable(
            "Веб-поиск выключен: в .env нет FIRECRAWL_API_KEY"
        )

    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(
                API_URL,
                headers={"Authorization": f"Bearer {settings.firecrawl_api_key}"},
                json={
                    "query": query,
                    "limit": limit,
                    "scrapeOptions": {"formats": ["markdown"]},
                },
            )
    except httpx.TimeoutException as exc:
        raise SearchUnavailable(f"Поиск не ответил за {TIMEOUT_SECONDS:.0f} секунд") from exc
    except httpx.HTTPError as exc:
        raise SearchUnavailable(f"Поиск недоступен: {exc}") from exc

    if response.status_code == 401:
        raise SearchUnavailable("Firecrawl не принял ключ — проверьте FIRECRAWL_API_KEY")
    if response.status_code == 429:
        raise SearchUnavailable("Firecrawl: лимит запросов исчерпан")
    if response.status_code >= 400:
        raise SearchUnavailable(f"Firecrawl вернул {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise SearchUnavailable("Firecrawl вернул не JSON") from exc

    results = _parse(payload)
    logger.info("Веб-поиск «%s»: %d результатов", query, len(results))
    return results


def search_sync(query: str, limit: int = DEFAULT_LIMIT) -> list[SearchResult]:
    """Синхронная обёртка — для команд CLI и проверок вручную."""
    return asyncio.run(search(query, limit))


# Описание инструмента для модели. Формат общий для OpenAI/DeepSeek.
#
# В описании сказано, КОГДА звать, а не только что делает: без этого модель
# либо не зовёт вовсе, либо зовёт на каждый вопрос, включая те, где ответ
# она и так знает.
TOOL_SPEC: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Ищет в интернете и возвращает выдержки со ссылками. "
            "Зови, когда ответ зависит от сведений, которых у тебя может не быть: "
            "события последнего времени, текущие цены и курсы, состояние сервисов, "
            "свежие версии и документация, любые факты, которые могли измениться. "
            "Не зови, если вопрос про уже сказанное в этом разговоре, про общие "
            "знания или про содержимое системы — там есть своя память."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Поисковый запрос обычными словами, как ищет человек",
                },
                "limit": {
                    "type": "integer",
                    "description": f"Сколько результатов вернуть, 1..{MAX_LIMIT}",
                    "default": DEFAULT_LIMIT,
                },
            },
            "required": ["query"],
        },
    },
}


async def run_tool(arguments: dict[str, Any]) -> str:
    """Выполняет вызов инструмента и складывает ответ для модели.

    Ошибку возвращаем текстом, а не исключением: модель должна узнать, что
    поиск не удался, и сказать об этом человеку, а не молча ответить по памяти.
    """
    try:
        results = await search(
            str(arguments.get("query", "")),
            int(arguments.get("limit") or DEFAULT_LIMIT),
        )
    except SearchUnavailable as exc:
        return f"ПОИСК НЕ УДАЛСЯ: {exc}. Скажи об этом человеку, не выдумывай факты."
    except Exception as exc:  # неожиданное — тоже не роняем диалог
        logger.exception("Веб-поиск упал неожиданно")
        return f"ПОИСК НЕ УДАЛСЯ: {exc}. Скажи об этом человеку, не выдумывай факты."

    if not results:
        return "Ничего не найдено. Скажи об этом прямо, не выдумывай факты."

    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"[{i}] {r.title}\n{r.url}\n{r.snippet}")
    return "\n\n".join(parts)
