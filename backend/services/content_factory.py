"""Nexus Content Factory — идея -> сценарий -> голос/картинка/видео -> approve.

Заявлено фаундером 22.08.2026 как «контент завод»: полный конвейер тренд ->
сценарий/картинка/голос -> видео -> approval -> календарь -> публикация ->
аналитика, собранный из нескольких внешних open-source репозиториев
(SocialFlow/VidPipe/OpenSocial/Social Agent AI/GenLab, см. память
nexus-os-content-factory-idea). Решено начать с узкого среза без единого
внешнего репозитория и без автопубликации:

    идея -> N сценариев (LLM) -> озвучка (tts.py, тот же движок, что у
    Джарвиса) -> картинка/видео (fal.ai) -> черновик ждёт approve/reject
    человеком -> готовые файлы отдаются фаундеру, публикует он сам.

Автопубликация в соцсети НЕ входит — фаундер прямо потребовал, что ничего
не публикуется без его подтверждения, а интеграций с площадками (OAuth и
т.п.) в системе пока просто нет.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..core import llmjson
from ..core.config import DATA_DIR, ensure_data_dir
from ..core.errors import NotFoundError, ValidationError
from ..core.jsonio import read_json, write_json
from ..models.schemas import ContentItem, ContentStatus

logger = logging.getLogger(__name__)

CONTENT_FILE = DATA_DIR / "content_items.json"

FAL_IMAGE_MODEL = "fal-ai/flux/schnell"
FAL_VIDEO_MODEL = "fal-ai/ltx-video"
FAL_QUEUE_POLL_SECONDS = 3
FAL_QUEUE_MAX_POLLS = 100  # ~5 минут — видео у fal.ai обычно готово раньше


def _load() -> list[dict]:
    ensure_data_dir()
    return read_json(CONTENT_FILE, []) or []


def _save(items: list[dict]) -> None:
    ensure_data_dir()
    write_json(CONTENT_FILE, items)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_items(status: str | None = None) -> list[ContentItem]:
    items = [ContentItem(**i) for i in _load()]
    if status:
        items = [i for i in items if i.status.value == status]
    return sorted(items, key=lambda i: i.created_at, reverse=True)


def get_item(item_id: str) -> ContentItem:
    for i in _load():
        if i["id"] == item_id:
            return ContentItem(**i)
    raise NotFoundError("ContentItem", item_id)


def _parse_plan(raw: str) -> list[dict]:
    """Разбирает JSON-ответ модели в список сценариев.

    Все капризы модели (```-обрамление, болтовня вокруг, обёртка под
    произвольным ключом, одиночный сценарий без массива) живут в общем
    core/llmjson — раньше каждый модуль знал только те из них, на которых
    успел обжечься сам.

    В отличие от Исследователя, пустой список здесь — ошибка: попросили
    сценарии, получили ноль, значит создавать нечего и надо сказать честно.
    """
    try:
        items = llmjson.parse_list(raw, item_hint="script")
    except llmjson.LLMJsonError as e:
        raise ValidationError(str(e)) from e

    if not items:
        raise ValidationError("Модель не вернула ни одного сценария")
    return items


async def generate_plan(
    topic: str,
    count: int = 3,
    platforms: list[str] | None = None,
    llm=None,
    scheduled_at: str | None = None,
) -> list[ContentItem]:
    """Идея -> N черновиков сценариев через LLM.

    Голос синтезируется отдельным шагом (synthesize_voice), не здесь —
    чтобы медленная/упавшая озвучка одного черновика не проваливала весь
    план и не блокировала остальные.

    scheduled_at ставит всем черновикам плана одну дату сразу: фаундер
    задаёт её в форме создания («хочу контент на 27-е»), и заставлять его
    потом проставлять дату каждому черновику руками — лишний шаг.
    """
    if not topic or not topic.strip():
        raise ValidationError("Нужна тема для плана контента")
    count = max(1, min(int(count), 10))
    platforms = platforms or ["tiktok", "instagram"]

    # Дату проверяем ДО обращения к модели: иначе фаундер платит за N
    # сценариев и получает отказ уже после генерации.
    if scheduled_at:
        _parse_when(scheduled_at)

    if llm is None:
        from .llm import LLMService
        from ..core.config import settings

        # LLMService() без аргументов берёт NEXSYS_LLM_PROVIDER=ollama из
        # .env — дешёвый вариант, но локальный Ollama на этой машине не
        # поднят. Настоящие персоны (Orpheus и др.) все сидят на
        # deepseek-chat с ключом DEEPSEEK_API_KEY (persona_manager.py) —
        # берём тот же провайдер, а не ловим ConnectError в проде.
        llm = LLMService(
            provider="deepseek",
            model="deepseek-chat",
            api_key=settings.deepseek_api_key,
        )

    from . import budget

    prompt = (
        f"Придумай {count} коротких видео-сценария на тему «{topic}» "
        f"для площадок: {', '.join(platforms)}.\n"
        'Ответь ТОЛЬКО JSON-массивом объектов вида '
        '{"script": "текст сценария для озвучки, 2-4 предложения", '
        '"caption": "подпись к посту", "hashtags": ["тег1", "тег2"]}. '
        "Без пояснений вокруг JSON, без markdown-обрамления."
    )
    raw = await llm.generate_response(prompt, kind=budget.BACKGROUND, json_mode=True)
    drafts = _parse_plan(raw)

    items = _load()
    created: list[ContentItem] = []
    for d in drafts[:count]:
        item = ContentItem(
            id=str(uuid.uuid4())[:8],
            topic=topic,
            script=str(d.get("script", "")).strip(),
            caption=str(d.get("caption", "")).strip(),
            hashtags=[str(h) for h in d.get("hashtags", [])],
            platforms=platforms,
            scheduled_at=scheduled_at,
            status=ContentStatus.SCHEDULED if scheduled_at else ContentStatus.DRAFT,
        )
        items.append(item.model_dump())
        created.append(item)
    _save(items)
    logger.info("Content Factory: создано %d черновиков по теме «%s»", len(created), topic)
    return created


def _content_dir() -> Path:
    from . import artifacts

    path = artifacts.artifacts_dir() / "content"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def synthesize_voice(item_id: str) -> ContentItem:
    """Озвучивает сценарий черновика тем же движком, что и голос Джарвиса
    (services.tts) — заводить второй голосовой движок незачем."""
    from . import tts

    item = get_item(item_id)
    if not item.script:
        raise ValidationError("У черновика нет сценария для озвучки")

    tmp_path = await tts.synthesize(item.script)
    dest = _content_dir() / f"{item.id}{tmp_path.suffix}"
    tmp_path.replace(dest)

    items = _load()
    for i in items:
        if i["id"] == item_id:
            i["voice_file"] = dest.name
            i["updated_at"] = _now()
            _save(items)
            return ContentItem(**i)
    raise NotFoundError("ContentItem", item_id)


def voice_file_path(item_id: str) -> Path:
    item = get_item(item_id)
    if not item.voice_file:
        raise ValidationError(f"Озвучка ещё не готова для черновика «{item_id}»")
    path = _content_dir() / item.voice_file
    if not path.is_file():
        raise NotFoundError("Файл озвучки", item.voice_file)
    return path


def _fal_headers() -> dict:
    from ..core.config import settings

    if not settings.fal_api_key:
        raise ValidationError(
            "Генерация картинок/видео выключена: не задан FAL_KEY в .env"
        )
    return {"Authorization": f"Key {settings.fal_api_key}"}


async def _fal_download(client: httpx.AsyncClient, url: str, dest: Path) -> None:
    resp = await client.get(url)
    resp.raise_for_status()
    dest.write_bytes(resp.content)


def _set_field(item_id: str, field: str, value: str) -> ContentItem:
    items = _load()
    for i in items:
        if i["id"] == item_id:
            i[field] = value
            i["updated_at"] = _now()
            _save(items)
            return ContentItem(**i)
    raise NotFoundError("ContentItem", item_id)


async def generate_image(item_id: str, prompt: str | None = None) -> ContentItem:
    """Картинка для черновика через fal.ai (flux/schnell, синхронный вызов —
    обычно готово за пару секунд, отдельная очередь не нужна)."""
    item = get_item(item_id)
    headers = _fal_headers()
    prompt = prompt or item.script or item.topic
    if not prompt:
        raise ValidationError("Нужен сценарий или тема, чтобы придумать картинку")

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"https://fal.run/{FAL_IMAGE_MODEL}",
            headers=headers,
            json={"prompt": prompt, "image_size": "portrait_16_9"},
        )
        resp.raise_for_status()
        data = resp.json()
        images = data.get("images") or []
        if not images:
            raise ValidationError("fal.ai не вернул картинку")

        dest = _content_dir() / f"{item.id}.jpg"
        await _fal_download(client, images[0]["url"], dest)

    logger.info("Content Factory: картинка готова для «%s»", item_id)
    return _set_field(item_id, "image_file", dest.name)


def carousel_dir(item_id: str) -> Path:
    """Своя папка на черновик: слайдов до десяти, и вперемешку с озвучкой и
    видео в общей папке их было бы не разобрать ни глазом, ни кодом."""
    path = _content_dir() / f"{item_id}-carousel"
    path.mkdir(parents=True, exist_ok=True)
    return path


def generate_carousel(item_id: str, style: str | None = None) -> ContentItem:
    """Собирает карусель из сценария черновика: слайды рисуются локально.

    Не async и без сети: рисование — счёт на процессоре, а не поход наружу
    (почему не генерируем слайды моделью — в шапке services/carousel.py).
    Ручка зовёт это через to_thread, чтобы не держать event loop.
    """
    from . import carousel as C

    item = get_item(item_id)
    if not item.script:
        raise ValidationError("Нужен сценарий, чтобы собрать карусель")

    chosen = style or item.carousel_style or C.DEFAULT_STYLE
    if chosen not in C.STYLES:
        raise ValidationError(
            f"Неизвестный стиль «{chosen}». Есть: {', '.join(C.STYLES)}"
        )

    # Поле «хук» появилось в системе позже карусели — берём его мягко,
    # чтобы код работал и на черновиках, созданных до него.
    hook = (getattr(item, "hook", "") or "").strip()

    deck = C.from_content(
        topic=item.topic,
        script=item.script,
        hook=hook,
        style=chosen,
        handle=channel_handle(),
        cover=C.cover_photo(),
    )

    out = carousel_dir(item_id)
    # Прошлая сборка могла дать больше слайдов, чем новая: не убрав старые,
    # получим карусель из смеси двух версий — на глаз это заметно не сразу.
    for stale in out.glob("*.jpg"):
        stale.unlink()

    paths = C.render(deck, out, prefix="slide")
    names = [p.name for p in paths]

    items = _load()
    for i in items:
        if i["id"] == item_id:
            i["carousel_files"] = names
            i["carousel_style"] = chosen
            i["updated_at"] = _now()
            _save(items)
            logger.info("Content Factory: карусель из %d слайдов для «%s»", len(names), item_id)
            return ContentItem(**i)
    raise NotFoundError("ContentItem", item_id)


def channel_handle() -> str:
    """Подпись канала в подвале слайда. Пусто — подвал остаётся без неё."""
    import os

    return os.getenv("NEXUS_CHANNEL_HANDLE", "").strip()


def carousel_slide_path(item_id: str, number: int) -> Path:
    """Путь к слайду по его номеру в карусели (с единицы, как на экране)."""
    item = get_item(item_id)
    if not item.carousel_files:
        raise ValidationError(f"Карусель ещё не собрана для черновика «{item_id}»")
    if not 1 <= number <= len(item.carousel_files):
        raise NotFoundError("Слайд карусели", f"{item_id}#{number}")
    path = carousel_dir(item_id) / item.carousel_files[number - 1]
    if not path.is_file():
        raise NotFoundError("Файл слайда", item.carousel_files[number - 1])
    return path


def image_file_path(item_id: str) -> Path:
    item = get_item(item_id)
    if not item.image_file:
        raise ValidationError(f"Картинка ещё не готова для черновика «{item_id}»")
    path = _content_dir() / item.image_file
    if not path.is_file():
        raise NotFoundError("Файл картинки", item.image_file)
    return path


async def generate_video(item_id: str, prompt: str | None = None) -> ContentItem:
    """Видео для черновика через fal.ai (ltx-video, очередь — генерация
    видео не укладывается в разумный синхронный HTTP-таймаут)."""
    item = get_item(item_id)
    headers = _fal_headers()
    prompt = prompt or item.script or item.topic
    if not prompt:
        raise ValidationError("Нужен сценарий или тема, чтобы придумать видео")

    async with httpx.AsyncClient(timeout=60.0) as client:
        submit = await client.post(
            f"https://queue.fal.run/{FAL_VIDEO_MODEL}",
            headers=headers,
            json={"prompt": prompt},
        )
        submit.raise_for_status()
        job = submit.json()
        status_url = job["status_url"]
        response_url = job["response_url"]

        for _ in range(FAL_QUEUE_MAX_POLLS):
            status = await client.get(status_url, headers=headers)
            status.raise_for_status()
            state = status.json().get("status")
            if state == "COMPLETED":
                break
            if state in ("ERROR", "CANCELLED"):
                raise ValidationError(f"fal.ai не смог сделать видео: {state}")
            await asyncio.sleep(FAL_QUEUE_POLL_SECONDS)
        else:
            raise ValidationError("fal.ai не успел сделать видео за отведённое время")

        result = await client.get(response_url, headers=headers)
        result.raise_for_status()
        video = (result.json().get("video") or {}).get("url")
        if not video:
            raise ValidationError("fal.ai не вернул видео")

        dest = _content_dir() / f"{item.id}.mp4"
        await _fal_download(client, video, dest)

    logger.info("Content Factory: видео готово для «%s»", item_id)
    return _set_field(item_id, "video_file", dest.name)


def video_file_path(item_id: str) -> Path:
    item = get_item(item_id)
    if not item.video_file:
        raise ValidationError(f"Видео ещё не готово для черновика «{item_id}»")
    path = _content_dir() / item.video_file
    if not path.is_file():
        raise NotFoundError("Файл видео", item.video_file)
    return path


def _parse_when(value: str) -> datetime:
    """Разбирает время публикации, отвергая мусор вместо тихого None.

    Голосовая команда доходит сюда уже в ISO — но через API дату может
    прислать кто угодно, а расписание с непонятной датой означает, что
    напоминание не придёт вообще.
    """
    if not value or not str(value).strip():
        raise ValidationError("Нужна дата и время публикации")
    try:
        when = datetime.fromisoformat(str(value).strip())
    except ValueError as e:
        raise ValidationError(f"Не понял дату публикации «{value}»: {e}") from e
    # Наивное время трактуем как UTC: всё хранилище живёт в UTC (_now).
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when


def schedule_item(item_id: str, scheduled_at: str) -> ContentItem:
    """Ставит черновик на дату публикации и переводит в SCHEDULED."""
    when = _parse_when(scheduled_at)
    if when < datetime.now(timezone.utc):
        raise ValidationError(
            f"Дата публикации «{scheduled_at}» уже прошла — напоминание не сработает"
        )

    items = _load()
    for i in items:
        if i["id"] == item_id:
            i["scheduled_at"] = scheduled_at
            i["status"] = ContentStatus.SCHEDULED.value
            i["updated_at"] = _now()
            _save(items)
            logger.info("Content Factory: черновик «%s» назначен на %s", item_id, scheduled_at)
            return ContentItem(**i)
    raise NotFoundError("ContentItem", item_id)


def set_platforms(item_id: str, platforms: list[str]) -> ContentItem:
    """Меняет список площадок. Площадки здесь — намерение, а не интеграция:
    система никуда не публикует, она только помнит, куда собирался фаундер."""
    cleaned = [p.strip() for p in (platforms or []) if p and p.strip()]
    if not cleaned:
        raise ValidationError("Нужна хотя бы одна площадка")

    items = _load()
    for i in items:
        if i["id"] == item_id:
            i["platforms"] = cleaned
            i["updated_at"] = _now()
            _save(items)
            return ContentItem(**i)
    raise NotFoundError("ContentItem", item_id)


def mark_posted(item_id: str) -> ContentItem:
    """Фаундер опубликовал руками и отметил это в интерфейсе."""
    return set_status(item_id, ContentStatus.POSTED)


def mark_reminded(item_id: str) -> ContentItem:
    """Отмечает, что напоминание «пора постить» ушло (см. content_reminder)."""
    return _set_field(item_id, "reminded_at", _now())


def due_items(now: datetime | None = None) -> list[ContentItem]:
    """Черновики, про которые пора напомнить: срок наступил, а он ещё не
    опубликован и не отклонён."""
    moment = now or datetime.now(timezone.utc)
    ripe: list[ContentItem] = []
    for raw in _load():
        if raw.get("status") != ContentStatus.SCHEDULED.value:
            continue
        when = raw.get("scheduled_at")
        if not when:
            continue
        try:
            parsed = _parse_when(when)
        except ValidationError:
            logger.warning("Черновик «%s» стоит на непонятной дате «%s»", raw.get("id"), when)
            continue
        if parsed <= moment:
            ripe.append(ContentItem(**raw))
    return ripe


async def send_for_approval(item_id: str) -> ContentItem:
    """Отправляет черновик кнопками в Telegram и ждёт ответа фаундера.

    Если сообщение не ушло (Telegram не настроен или лежит), черновик
    остаётся DRAFT: статус «ждёт подтверждения» без сообщения означал бы
    вечное ожидание ответа, которого некому дать.
    """
    from . import telegram_notify

    item = get_item(item_id)
    sent = await telegram_notify.send_approval_request(item)
    if not sent:
        logger.warning("Черновик «%s» не ушёл в Telegram — оставляем в черновиках", item_id)
        return item
    return set_status(item_id, ContentStatus.PENDING_APPROVAL)


def set_status(item_id: str, status: ContentStatus) -> ContentItem:
    items = _load()
    for i in items:
        if i["id"] == item_id:
            i["status"] = status.value
            i["updated_at"] = _now()
            _save(items)
            return ContentItem(**i)
    raise NotFoundError("ContentItem", item_id)


def delete_item(item_id: str) -> bool:
    items = _load()
    target = next((i for i in items if i["id"] == item_id), None)
    if target is None:
        raise NotFoundError("ContentItem", item_id)
    for field in ("voice_file", "image_file", "video_file"):
        if target.get(field):
            path = _content_dir() / target[field]
            if path.is_file():
                path.unlink()
    _save([i for i in items if i["id"] != item_id])
    return True
