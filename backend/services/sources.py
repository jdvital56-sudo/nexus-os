"""Библиотека источников — каталог сайтов, за которыми система следит сама.

Хранит не содержимое, а список адресов: что читать, как часто и насколько
этому можно верить. Исследователь берёт отсюда очередь обхода вместо того,
чтобы ходить по интернету наугад.
"""
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from ..core.config import DATA_DIR, ensure_data_dir
from ..core.errors import ConflictError, NotFoundError, ValidationError
from ..core.jsonio import read_json, write_json
from ..models.schemas import Source, SourceCreate, SourceStatus, SourceUpdate

SOURCES_FILE = DATA_DIR / "sources.json"

# Столько провалов подряд — и источник уходит в карантин. Мёртвая ссылка,
# которую агент дёргает по расписанию, жжёт кредиты Firecrawl впустую.
MAX_ERROR_STREAK = 5


def _load() -> list[dict]:
    ensure_data_dir()
    return read_json(SOURCES_FILE, [])


def _save(sources: list[dict]):
    ensure_data_dir()
    write_json(SOURCES_FILE, sources)


def normalize_url(url: str) -> str:
    """Приводит адрес к виду, по которому ищем дубли.

    Схема и хост в нижний регистр, хвостовой слэш и якорь долой. Путь и
    параметры трогать нельзя — это разные страницы.
    """
    raw = (url or "").strip()
    if not raw:
        raise ValidationError("Адрес источника пустой")

    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https"):
        raise ValidationError(f"Адрес должен начинаться с http:// или https:// — получено: {url!r}")
    if not parts.netloc:
        raise ValidationError(f"В адресе нет домена: {url!r}")

    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def _clamp_trust(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _validate_interval(hours: int) -> int:
    if int(hours) < 1:
        raise ValidationError("Интервал обхода не может быть меньше часа")
    return int(hours)


def list_sources(
    topic: str | None = None,
    kind: str | None = None,
    enabled_only: bool = False,
) -> list[Source]:
    sources = [Source(**s) for s in _load()]
    if topic:
        sources = [s for s in sources if topic in s.topics]
    if kind:
        sources = [s for s in sources if s.kind.value == kind]
    if enabled_only:
        sources = [s for s in sources if s.enabled]
    return sources


def get_source(source_id: str) -> Source:
    for s in _load():
        if s["id"] == source_id:
            return Source(**s)
    raise NotFoundError("Source", source_id)


def add_source(data: SourceCreate) -> Source:
    url = normalize_url(data.url)
    sources = _load()

    for existing in sources:
        if existing["url"] == url:
            raise ConflictError(f"Источник уже в библиотеке: {url} (id: {existing['id']})")

    source = Source(
        id=str(uuid.uuid4())[:8],
        url=url,
        title=data.title or urlsplit(url).netloc,
        kind=data.kind,
        topics=data.topics,
        trust=_clamp_trust(data.trust),
        check_interval_hours=_validate_interval(data.check_interval_hours),
        enabled=data.enabled,
        notes=data.notes,
    )
    sources.append(source.model_dump())
    _save(sources)
    return source


def update_source(source_id: str, data: SourceUpdate) -> Source:
    sources = _load()
    for i, s in enumerate(sources):
        if s["id"] != source_id:
            continue

        if data.url is not None:
            new_url = normalize_url(data.url)
            for other in sources:
                if other["id"] != source_id and other["url"] == new_url:
                    raise ConflictError(f"Источник уже в библиотеке: {new_url} (id: {other['id']})")
            s["url"] = new_url
        if data.title is not None:
            s["title"] = data.title
        if data.kind is not None:
            s["kind"] = data.kind.value
        if data.topics is not None:
            s["topics"] = data.topics
        if data.trust is not None:
            s["trust"] = _clamp_trust(data.trust)
        if data.check_interval_hours is not None:
            s["check_interval_hours"] = _validate_interval(data.check_interval_hours)
        if data.enabled is not None:
            s["enabled"] = data.enabled
            # Ручное включение — это и есть помилование из карантина
            if data.enabled:
                s["error_streak"] = 0
        if data.notes is not None:
            s["notes"] = data.notes

        s["updated_at"] = datetime.utcnow().isoformat()
        sources[i] = s
        _save(sources)
        return Source(**s)
    raise NotFoundError("Source", source_id)


def delete_source(source_id: str) -> bool:
    sources = _load()
    rest = [s for s in sources if s["id"] != source_id]
    if len(rest) == len(sources):
        raise NotFoundError("Source", source_id)
    _save(rest)
    return True


def due_sources(now: datetime | None = None) -> list[Source]:
    """Очередь обхода: включённые источники, у которых вышел срок.

    Ни разу не проверенные идут первыми — про них система не знает ничего.
    """
    now = now or datetime.utcnow()
    due = []
    for s in list_sources(enabled_only=True):
        if s.last_checked_at is None:
            due.append(s)
            continue
        try:
            last = datetime.fromisoformat(s.last_checked_at)
        except ValueError:
            # Битая отметка времени — считаем, что источник не проверялся
            due.append(s)
            continue
        if last + timedelta(hours=s.check_interval_hours) <= now:
            due.append(s)
    return sorted(due, key=lambda s: (s.last_checked_at is not None, s.last_checked_at or ""))


def record_check(
    source_id: str,
    ok: bool,
    items_found: int = 0,
    error: str = "",
) -> Source:
    """Отмечает результат обхода. После MAX_ERROR_STREAK провалов — карантин."""
    sources = _load()
    for i, s in enumerate(sources):
        if s["id"] != source_id:
            continue

        s["last_checked_at"] = datetime.utcnow().isoformat()
        s["check_count"] = s.get("check_count", 0) + 1

        if ok:
            s["last_status"] = SourceStatus.OK.value
            s["last_error"] = ""
            s["error_streak"] = 0
            s["items_found"] = s.get("items_found", 0) + max(0, int(items_found))
        else:
            s["last_status"] = SourceStatus.ERROR.value
            s["last_error"] = error
            s["error_streak"] = s.get("error_streak", 0) + 1
            if s["error_streak"] >= MAX_ERROR_STREAK:
                s["enabled"] = False

        s["updated_at"] = datetime.utcnow().isoformat()
        sources[i] = s
        _save(sources)
        return Source(**s)
    raise NotFoundError("Source", source_id)


def get_stats() -> dict:
    sources = list_sources()
    return {
        "total": len(sources),
        "enabled": sum(1 for s in sources if s.enabled),
        "quarantined": sum(1 for s in sources if not s.enabled and s.error_streak >= MAX_ERROR_STREAK),
        "never_checked": sum(1 for s in sources if s.last_checked_at is None),
        "due_now": len(due_sources()),
        "topics": sorted({t for s in sources for t in s.topics}),
    }
