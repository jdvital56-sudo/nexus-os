"""Загрузка системных промптов ролей.

Промпт роли = общая часть (`_common.md`) + своя (`<key>.md`). Общая часть
описывает то, что одинаково у всех: как обращаться с файлами, что считать
недоверенными данными, когда останавливаться и спрашивать. Дублировать её
семь раз значило бы семь раз её и чинить.

Файлы, а не строки в коде: промпт — это то, что фаундер будет править сам,
без Python и без перезапуска сборки.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from . import config

ROLES_DIR = Path(__file__).resolve().parent / "roles"
COMMON = "_common.md"


class PromptMissing(RuntimeError):
    pass


@lru_cache(maxsize=32)
def _read(name: str) -> str:
    path = ROLES_DIR / name
    if not path.exists():
        raise PromptMissing(f"Нет файла промпта {path}")
    return path.read_text(encoding="utf-8").strip()


def load(role_key: str) -> str:
    role = config.get_role(role_key)
    common = _read(COMMON)
    own = _read(f"{role.key}.md")
    tool_list = "\n".join(f"- `{name}`" for name in role.tools)
    return (
        f"{own}\n\n---\n\n{common}\n\n"
        f"## Твои инструменты\n\n{tool_list}\n\n"
        "Инструментов, которых нет в этом списке, у тебя нет. Не проси их и не "
        "притворяйся, что вызвал."
    )


def reload() -> None:
    """Сбросить кэш — фаундер правит промпт и хочет увидеть эффект сразу."""
    _read.cache_clear()
