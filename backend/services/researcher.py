"""Исследователь — ищет тренды по направлениям фаундера и предлагает темы.

Тот самый TREND AGENT из первой формулировки контент-завода (22.08.2026):
до сих пор тема для сценариев приходила только голосом от фаундера, а
система сама ничего не предлагала. Теперь она смотрит, что происходит в
его нишах, и кладёт находки в раздел «Идеи» с пометкой «предложил Джарвис».

Отдельного хранилища для находок нет намеренно: «Идеи» ровно для этого и
заводились — то, что откладывается на будущее и ждёт решения человека
(см. services/ideas.py). Своё место здесь только у направлений поиска.

Публикует и решает по-прежнему человек: Исследователь не создаёт контент,
он приносит темы.
"""
import logging

from ..core import llmjson
from ..core.config import DATA_DIR, ensure_data_dir
from ..core.errors import ValidationError
from ..core.jsonio import read_json, write_json
from ..models.schemas import Idea
from . import ideas as ideas_svc
from . import websearch

logger = logging.getLogger(__name__)

DIRECTIONS_FILE = DATA_DIR / "content_directions.json"

# Сколько страниц выдачи скармливаем модели. Больше — дороже и шумнее:
# для «что сейчас обсуждают» хватает нескольких свежих источников.
SEARCH_LIMIT = 5

# Сколько тем просим за один заход. Десяток предложений в день фаундер не
# разберёт, а неразобранная очередь быстро превращается в мусор.
TOPICS_PER_RUN = 3

# Сколько уже предложенных тем показываем модели, чтобы она их не повторяла.
# Весь список слать нельзя — он растёт без предела и однажды съест промпт
# целиком; свежих хватает, старые темы к тому времени теряют актуальность.
RECENT_TOPICS_SHOWN = 40


def get_directions() -> list[str]:
    ensure_data_dir()
    stored = read_json(DIRECTIONS_FILE, []) or []
    return [str(d) for d in stored]


def set_directions(directions: list[str]) -> list[str]:
    """Сохраняет направления поиска, вычищая пустые и повторы.

    Пустой список после чистки — это не «выключить исследователя», а почти
    всегда опечатка в форме, поэтому отвергаем: выключение делается снятием
    всех направлений осознанно, через отдельную пустую отправку.
    """
    cleaned: list[str] = []
    for raw in directions or []:
        item = str(raw).strip()
        if item and item not in cleaned:
            cleaned.append(item)

    if directions and not cleaned:
        raise ValidationError("Направления пустые — нечего искать")

    ensure_data_dir()
    write_json(DIRECTIONS_FILE, cleaned)
    return cleaned


def _llm():
    """Тот же провайдер, что у контент-завода и персон.

    LLMService() без аргументов взял бы NEXSYS_LLM_PROVIDER=ollama из .env,
    а локальный Ollama на машине фаундера не поднят — см. подробный разбор
    в content_factory.generate_plan.
    """
    from ..core.config import settings
    from .llm import LLMService

    return LLMService(provider="deepseek", model="deepseek-chat", api_key=settings.deepseek_api_key)


def _normalize(topic: str) -> str:
    """Ключ сравнения тем: регистр и пробелы не делают тему новой."""
    return " ".join(str(topic).lower().split())


def _existing_topics() -> set[str]:
    return {_normalize(i.content) for i in ideas_svc.list_ideas()}


def _parse_topics(raw: str) -> list[dict]:
    """Разбирает ответ модели. Пустой список — законное «нового нет».

    Мусор вместо JSON — ошибка: молча вернуть пустоту значит показать
    фаундеру «трендов нет», когда на самом деле сломался разбор.
    """
    try:
        return llmjson.parse_list(raw, item_hint="topic")
    except llmjson.LLMJsonError as e:
        raise ValidationError(str(e)) from e


async def research(direction: str, llm=None) -> list[Idea]:
    """Смотрит, что происходит по направлению, и предлагает темы контента.

    Повторы отсеиваются по уже записанным идеям: утренний прогон не должен
    каждый день приносить одно и то же.
    """
    direction = (direction or "").strip()
    if not direction:
        raise ValidationError("Нужно направление поиска")

    try:
        results = await websearch.search(
            f"{direction} тренды 2026 что обсуждают сейчас", limit=SEARCH_LIMIT
        )
    except websearch.SearchUnavailable as e:
        # Молча вернуть пустой список нельзя: фаундер решит, что трендов
        # просто нет, и не узнает, что поиск отвалился.
        raise ValidationError(f"Веб-поиск недоступен: {e}") from e

    if not results:
        logger.info("Исследователь: по «%s» выдача пустая", direction)
        return []

    digest = "\n\n".join(f"{r.title}\n{r.url}\n{r.snippet}" for r in results)

    # Сравнения строк мало: модель переформулирует ту же мысль другими
    # словами, и очередь идей копится дублями (найдено живым прогоном
    # 24.08.2026). Единственный, кто видит, что это одно и то же, — она сама.
    already = [i.content for i in ideas_svc.list_ideas()][:RECENT_TOPICS_SHOWN]
    avoid = ""
    if already:
        listed = "\n".join(f"- {t}" for t in already)
        avoid = (
            f"\nЭти темы уже предложены раньше — не предлагай их снова, "
            f"даже другими словами и с другого угла:\n{listed}\n"
        )

    prompt = (
        f"Ты ищешь темы для коротких видео по направлению «{direction}».\n\n"
        f"Свежие материалы из поиска:\n{digest}\n"
        f"{avoid}\n"
        f"Опираясь ТОЛЬКО на эти материалы, предложи до {TOPICS_PER_RUN} тем, "
        "которые сейчас откликнутся аудитории. Не выдумывай фактов, которых "
        "нет в материалах. Если всё стоящее уже предложено раньше — верни "
        "пустой массив, это нормальный ответ.\n"
        'Ответь ТОЛЬКО JSON-массивом вида '
        '{"topic": "тема одной строкой", "why": "почему она сейчас зайдёт"}. '
        "Без пояснений вокруг JSON, без markdown-обрамления."
    )

    from . import budget

    llm = llm or _llm()
    raw = await llm.generate_response(prompt, kind=budget.BACKGROUND, json_mode=True)
    proposals = _parse_topics(raw)

    seen = _existing_topics()
    created: list[Idea] = []
    for p in proposals[:TOPICS_PER_RUN]:
        topic = str(p.get("topic", "")).strip()
        if not topic or _normalize(topic) in seen:
            continue
        seen.add(_normalize(topic))
        why = str(p.get("why", "")).strip()
        context = f"Исследователь, направление «{direction}»"
        if why:
            context = f"{context}. {why}"
        created.append(ideas_svc.propose(topic, context=context))

    logger.info("Исследователь: по «%s» предложено %d тем", direction, len(created))
    return created


async def daily_sweep() -> int:
    """Утренний обход всех направлений. Возвращает число новых идей.

    Упавшее направление не рушит остальные: сеть моргнула на первом — надо
    всё равно посмотреть второе, иначе один сбой оставляет фаундера совсем
    без предложений.
    """
    directions = get_directions()
    if not directions:
        return 0

    total = 0
    llm = _llm()
    for direction in directions:
        try:
            total += len(await research(direction, llm=llm))
        except Exception:
            logger.exception("Исследователь: направление «%s» не отработало", direction)

    if total:
        logger.info("Исследователь: за утро предложено %d тем", total)
    return total
