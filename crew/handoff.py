"""Передача работы между ролями — файлом, а не сообщением.

Так это устроено в разобранном видео, и это правильно: передача переживает
перезапуск, читается человеком без программиста, ложится в git и поддаётся
разбору через неделю. Шину сообщений здесь строить незачем.

Одно отличие от оригинала, сделанное сознательно. В видео получатель читает
файл прямо в папке отправителя (`/srv/hermes-creative/workspace/docs/...`) —
значит, все агенты видят диски друг друга, и песочницы нет. Здесь передача
**копирует** содержимое в инбокс получателя. Три следствия: изоляция ролей
остаётся настоящей; передача самодостаточна и не ломается, когда отправитель
перепишет свой файл; спор «что именно было передано» решается файлом, а не
памятью.

Гонок нет по построению: у каждой передачи своё имя (время + случайный
суффикс), один писатель, запись атомарная, статус выражается перемещением
папки `handoffs/ -> done/`, а не полем внутри общего файла. Общего
изменяемого состояния в протоколе нет вовсе.
"""
from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .workspace import Workspace, WorkspaceError

SLUG_RE = re.compile(r"[^a-z0-9-]+")


class HandoffError(RuntimeError):
    """Передача невозможна: нет адресата, нет файла, роль не принимает."""


def slugify(value: str) -> str:
    """Ключ проекта. Один и тот же slug связывает папки всех ролей."""
    lowered = (value or "").strip().lower()
    # Транслитерация только того, что реально приходит: русские названия брендов.
    table = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    lowered = "".join(table.get(ch, ch) for ch in lowered)
    slug = SLUG_RE.sub("-", lowered).strip("-")
    if not slug:
        raise HandoffError(f"Не смог сделать ключ проекта из «{value}».")
    return slug[:60]


def new_id() -> str:
    """Время в UTC + случайный хвост. Сортируется по времени, не сталкивается."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


@dataclass
class Handoff:
    handoff_id: str
    project: str
    from_role: str
    to_role: str
    created_at: str
    summary: str
    main_file: str
    """Имя главного файла внутри папки `files/` этой передачи."""
    attachments: list[str]
    request: str
    """Что именно просят сделать. Без этого получатель угадывает."""

    def to_markdown(self) -> str:
        head = json.dumps(
            {k: v for k, v in asdict(self).items() if k not in ("summary", "request")},
            ensure_ascii=False,
            indent=2,
        )
        from_title = config.get_role(self.from_role).title
        to_title = config.get_role(self.to_role).title
        return (
            f"# Передача {self.handoff_id}\n\n"
            f"**От:** {from_title} → **Кому:** {to_title}\n"
            f"**Проект:** `{self.project}`\n\n"
            f"## Что просят сделать\n\n{self.request.strip()}\n\n"
            f"## Что передано\n\n{self.summary.strip()}\n\n"
            f"## Файлы\n\n"
            + "\n".join(f"- `files/{name}`" for name in [self.main_file, *self.attachments])
            + f"\n\n## Служебное\n\n```json\n{head}\n```\n"
        )


def submit(
    *,
    from_role: str,
    to_role: str,
    project: str,
    summary: str,
    request: str,
    main_file: str,
    attachments: list[str] | None = None,
) -> Handoff:
    """Скопировать работу в инбокс получателя и вернуть запись о передаче.

    `main_file` и `attachments` — пути внутри песочницы ОТПРАВИТЕЛЯ. Наружу
    он их отдать не может; копируем мы, проверив каждый путь его же
    песочницей.
    """
    sender_role = config.get_role(from_role)
    target = config.get_role(to_role)

    if target.key not in sender_role.hands_to:
        allowed = ", ".join(config.get_role(k).title for k in sender_role.hands_to) or "никому"
        raise HandoffError(
            f"{sender_role.title} не передаёт работу роли «{target.title}». "
            f"Разрешено: {allowed}."
        )
    if sender_role.key not in target.accepts_from:
        raise HandoffError(
            f"{target.title} не принимает работу от роли «{sender_role.title}»."
        )

    sender_ws = Workspace(sender_role.key)
    slug = slugify(project)
    handoff_id = new_id()

    inbox = config.workspace_of(target.key) / "docs" / "inbox" / "handoffs" / handoff_id
    files_dir = inbox / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    def copy_in(relative: str) -> str:
        try:
            source = sender_ws.resolve(relative)
        except WorkspaceError as exc:
            raise HandoffError(str(exc)) from exc
        if not source.is_file():
            raise HandoffError(f"Нечего передавать: нет файла {relative}.")
        shutil.copy2(source, files_dir / source.name)
        return source.name

    main_name = copy_in(main_file)
    attached = [copy_in(item) for item in (attachments or []) if item and item != main_file]

    record = Handoff(
        handoff_id=handoff_id,
        project=slug,
        from_role=sender_role.key,
        to_role=target.key,
        created_at=datetime.now(timezone.utc).isoformat(),
        summary=summary,
        main_file=main_name,
        attachments=attached,
        request=request,
    )

    # Манифест пишем последним: пока его нет, папка считается недособранной,
    # и `pending()` её не покажет. Получатель не увидит половину передачи.
    Workspace._atomic_write(inbox / "handoff.md", record.to_markdown().encode("utf-8"))
    return record


def pending(role_key: str) -> list[dict]:
    """Непринятые передачи роли, старые первыми."""
    role = config.get_role(role_key)
    base = config.workspace_of(role.key) / "docs" / "inbox" / "handoffs"
    if not base.exists():
        return []
    out: list[dict] = []
    for entry in sorted(base.iterdir()):
        manifest = entry / "handoff.md"
        if not entry.is_dir() or not manifest.exists():
            continue
        out.append(
            {
                "handoff_id": entry.name,
                "path": f"docs/inbox/handoffs/{entry.name}/handoff.md",
                "meta": _read_meta(manifest),
            }
        )
    return out


def _read_meta(manifest: Path) -> dict:
    text = manifest.read_text(encoding="utf-8", errors="replace")
    start = text.rfind("```json")
    if start == -1:
        return {}
    end = text.find("```", start + 7)
    try:
        return json.loads(text[start + 7 : end])
    except (json.JSONDecodeError, ValueError):
        return {}


def accept(role_key: str, handoff_id: str) -> str:
    """Пометить передачу принятой, переместив её папку в `done/`.

    Статус — это местоположение, а не поле внутри файла. Поэтому нет
    read-modify-write, нет и гонки: два одновременных `accept` дадут один
    успех и одну честную ошибку, а не битый JSON.
    """
    role = config.get_role(role_key)
    base = config.workspace_of(role.key) / "docs" / "inbox"
    source = base / "handoffs" / handoff_id
    if not source.is_dir():
        raise HandoffError(f"Нет непринятой передачи {handoff_id}.")
    destination = base / "done" / handoff_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise HandoffError(f"Передача {handoff_id} уже принята.")
    source.rename(destination)
    return f"docs/inbox/done/{handoff_id}/handoff.md"
