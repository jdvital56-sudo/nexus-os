"""Загрузка системных промптов ролей.

Промпт роли = общая часть (`_common.md`) + своя (`<key>.md`). Общая часть
описывает то, что одинаково у всех: как обращаться с файлами, что считать
недоверенными данными, когда останавливаться и спрашивать. Дублировать её
семь раз значило бы семь раз её и чинить.

Файлы, а не строки в коде: промпт — это то, что фаундер будет править сам,
без Python и без перезапуска сборки.

**Кэш следит за временем правки файла.** Обычный `lru_cache` здесь — ловушка:
поправил промпт, а живой бот продолжает работать на старом тексте, и правка
выглядит как «ничего не изменилось». У этого проекта такое уже было с
Electron-виджетом, который крутил старый фронтенд. Здесь дороже: промпт
правится часто, а расхождение видно только по поведению модели.
"""
from __future__ import annotations

from pathlib import Path

from . import config

ROLES_DIR = Path(__file__).resolve().parent / "roles"
COMMON = "_common.md"

# имя файла -> (время правки, текст)
_cache: dict[str, tuple[float, str]] = {}


class PromptMissing(RuntimeError):
    pass


def _read(name: str) -> str:
    path = ROLES_DIR / name
    if not path.exists():
        raise PromptMissing(f"Нет файла промпта {path}")

    stamp = path.stat().st_mtime
    cached = _cache.get(name)
    if cached is not None and cached[0] == stamp:
        return cached[1]

    text = path.read_text(encoding="utf-8").strip()
    _cache[name] = (stamp, text)
    return text


def load(role_key: str) -> str:
    role = config.get_role(role_key)
    common = _read(COMMON)
    own = _read(f"{role.key}.md")
    refs = "".join(f"\n\n---\n\n{_read(name)}" for name in role.references)
    tool_list = "\n".join(f"- `{name}`" for name in role.tools)
    return (
        f"{own}{refs}\n\n---\n\n{common}\n\n"
        f"## Твои инструменты\n\n{tool_list}\n\n"
        "Инструментов, которых нет в этом списке, у тебя нет. Не проси их и не "
        "притворяйся, что вызвал."
    )


def reload() -> None:
    """Сбросить кэш принудительно. Обычно не нужен — время правки и так следит."""
    _cache.clear()
