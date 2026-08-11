"""Единая папка артефактов: всё, что система сгенерировала для человека.

Три правила, которые здесь держатся:

1. Имя файла — kebab-case, предсказуемое и без сюрпризов в путях.
2. Заголовок и описание обязательны. Файл без описания через месяц
   становится мусором, который страшно удалить и незачем хранить.
3. Удаление — только по явному подтверждению человека (хартия §6, п.3).
   Система умеет пометить артефакт к удалению, но не стереть его сама.
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..core.config import DATA_DIR, ensure_data_dir, settings
from ..core.errors import NotFoundError
from ..core.jsonio import read_json, write_json

logger = logging.getLogger(__name__)

REGISTRY_FILE = DATA_DIR / "artifacts.json"

# Временные файлы (скачанные голосовые и прочее) живут отдельно и в реестр
# не попадают — это не артефакты, а мусор процесса
TEMP_SUBDIR = ".tmp"

STATUS_ACTIVE = "active"
STATUS_PENDING_DELETE = "pending_delete"


def artifacts_dir() -> Path:
    path = Path(settings.artifacts_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def temp_dir() -> Path:
    path = artifacts_dir() / TEMP_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(title: str) -> str:
    """kebab-case из заголовка, кириллица сохраняется как есть."""
    slug = title.strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug, flags=re.UNICODE)
    slug = re.sub(r"[\s_]+", "-", slug, flags=re.UNICODE)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:80] or "artifact"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> list[dict]:
    ensure_data_dir()
    return read_json(REGISTRY_FILE, []) or []


def _save(items: list[dict]) -> None:
    ensure_data_dir()
    write_json(REGISTRY_FILE, items)


def save(
    title: str,
    content: str,
    description: str,
    kind: str = "document",
    extension: str = "md",
    source: str = "",
) -> dict:
    """Сохранить артефакт. Без заголовка и описания не принимается."""
    if not title or not title.strip():
        raise ValueError("У артефакта должен быть заголовок")
    if not description or not description.strip():
        raise ValueError(
            "У артефакта должно быть описание: без него через месяц "
            "непонятно, что это и можно ли удалять"
        )

    stamp = datetime.now().strftime("%Y-%m-%d")
    name = f"{stamp}-{slugify(title)}.{extension.lstrip('.')}"
    path = artifacts_dir() / name

    # Не затираем чужой файл молча
    counter = 2
    while path.exists():
        path = artifacts_dir() / f"{stamp}-{slugify(title)}-{counter}.{extension.lstrip('.')}"
        counter += 1

    path.write_text(content, encoding="utf-8")

    item = {
        "id": str(uuid.uuid4())[:8],
        "title": title.strip(),
        "description": description.strip(),
        "kind": kind,
        "filename": path.name,
        "size_bytes": path.stat().st_size,
        "source": source,
        "status": STATUS_ACTIVE,
        "created_at": _now(),
        "delete_requested_at": None,
    }
    items = _load()
    items.append(item)
    _save(items)

    logger.info("Артефакт сохранён: %s (%s)", path.name, kind)
    return item


def list_artifacts(status: str | None = None, kind: str | None = None) -> list[dict]:
    items = _load()
    if status:
        items = [i for i in items if i["status"] == status]
    if kind:
        items = [i for i in items if i["kind"] == kind]
    return sorted(items, key=lambda i: i["created_at"], reverse=True)


def get_artifact(artifact_id: str) -> dict:
    for i in _load():
        if i["id"] == artifact_id:
            return i
    raise NotFoundError("Artifact", artifact_id)


def read_artifact(artifact_id: str) -> str:
    item = get_artifact(artifact_id)
    path = artifacts_dir() / item["filename"]
    if not path.is_file():
        raise FileNotFoundError(f"Файл артефакта пропал: {item['filename']}")
    return path.read_text(encoding="utf-8", errors="replace")


def request_delete(artifact_id: str, reason: str = "") -> dict:
    """Пометить к удалению. Файл остаётся на месте — решает человек."""
    items = _load()
    for i in items:
        if i["id"] == artifact_id:
            i["status"] = STATUS_PENDING_DELETE
            i["delete_requested_at"] = _now()
            i["delete_reason"] = reason
            _save(items)
            logger.info("Артефакт %s помечен к удалению: %s", artifact_id, reason)
            return i
    raise NotFoundError("Artifact", artifact_id)


def cancel_delete(artifact_id: str) -> dict:
    items = _load()
    for i in items:
        if i["id"] == artifact_id:
            i["status"] = STATUS_ACTIVE
            i["delete_requested_at"] = None
            i.pop("delete_reason", None)
            _save(items)
            return i
    raise NotFoundError("Artifact", artifact_id)


def delete(artifact_id: str, confirmed: bool = False) -> dict:
    """Удалить файл. Без confirmed=True не делает ничего (хартия §6, п.3)."""
    if not confirmed:
        raise PermissionError(
            "Удаление артефакта требует подтверждения человека: "
            "передайте confirmed=true"
        )

    items = _load()
    for index, i in enumerate(items):
        if i["id"] != artifact_id:
            continue
        path = artifacts_dir() / i["filename"]
        if path.is_file():
            path.unlink()
        items.pop(index)
        _save(items)
        logger.info("Артефакт %s удалён по подтверждению человека", artifact_id)
        return {"deleted": True, "id": artifact_id, "filename": i["filename"]}

    raise NotFoundError("Artifact", artifact_id)


def adopt_orphans() -> list[dict]:
    """Заносит в реестр файлы, появившиеся в папке мимо save().

    Такие файлы получают честную пометку в описании: система не знает,
    что это, и придумывать за автора не будет.
    """
    known = {i["filename"] for i in _load()}
    adopted = []

    for path in sorted(artifacts_dir().glob("*")):
        if not path.is_file() or path.name in known or path.name.startswith("."):
            continue
        item = {
            "id": str(uuid.uuid4())[:8],
            "title": path.stem,
            "description": "Файл появился в папке мимо реестра — назначение неизвестно",
            "kind": "unknown",
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "source": "adopted",
            "status": STATUS_ACTIVE,
            "created_at": datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
            "delete_requested_at": None,
        }
        items = _load()
        items.append(item)
        _save(items)
        adopted.append(item)

    return adopted
