"""Уроки роли: то, чем агент отличается сегодня от себя вчерашнего.

Модель не помнит прошлый прогон. «Агент обучается» без механизма — пустое
слово. Механизм такой: агент записывает урок в свой файл, файл подмешивается
в системный промпт следующего запуска. Тогда исправление, сделанное один раз,
держится дальше само.

Три правила, без которых это ломается — каждое взято из известного способа
сломать:

1. **Урок пишется только после поправки ЧЕЛОВЕКА.** Агент, которому позволено
   записывать собственные выводы, за неделю сочиняет себе свод правил из
   ничего и начинает ему следовать. Источник урока — всегда живой человек,
   сказавший «не так».

2. **Файл ограничен.** Тридцать уроков, каждый до 300 символов. Без потолка
   он растёт, вытесняет из промпта саму роль, и агент начинает соблюдать
   двадцать частных случаев вместо своей методики. При переполнении вытесняется
   самый старый — не потому что он неверный, а потому что за месяц он либо уже
   стал привычкой, либо не понадобился.

3. **Урок — это правило, а не история.** «Фаундеру не понравился кадр 3» —
   бесполезно. «Платье в промпте описывать дословно из Bible, пересказ даёт
   другой крой» — работает. Формат заставляет писать второе.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import date

from . import config
from .workspace import Workspace

MAX_LESSONS = 30
MAX_LESSON_CHARS = 300
LESSONS_PATH = "docs/lessons.md"


class LessonError(RuntimeError):
    pass


@dataclass
class Lesson:
    date: str
    rule: str
    """Правило в повелительном наклонении. То, что агент будет делать иначе."""
    because: str
    """Что именно пошло не так. Одна фраза, конкретная."""


def _path_for(role_key: str) -> str:
    config.get_role(role_key)
    return LESSONS_PATH


def load(role_key: str) -> list[Lesson]:
    ws = Workspace(role_key)
    try:
        text = ws.read(_path_for(role_key))
    except Exception:
        return []
    out: list[Lesson] = []
    for block in re.finditer(
        r"^- \*\*(\d{4}-\d{2}-\d{2})\*\* (.+?)\n  _причина:_ (.+?)$",
        text,
        re.M | re.S,
    ):
        out.append(Lesson(block.group(1), block.group(2).strip(), block.group(3).strip()))
    return out


def add(role_key: str, rule: str, because: str) -> str:
    rule = " ".join((rule or "").split())
    because = " ".join((because or "").split())
    if not rule:
        raise LessonError("Пустое правило записывать нельзя.")
    if len(rule) > MAX_LESSON_CHARS:
        raise LessonError(
            f"Правило длиннее {MAX_LESSON_CHARS} символов. Урок — это одна "
            "фраза, которую можно выполнить, а не пересказ разговора."
        )
    if not because:
        raise LessonError(
            "Не указано, что именно пошло не так. Правило без причины через "
            "месяц выглядит произволом, и его нарушат."
        )

    existing = load(role_key)
    normalized = rule.lower()
    if any(l.rule.lower() == normalized for l in existing):
        return "Такой урок уже записан, дубль не добавлен."

    existing.append(Lesson(date.today().isoformat(), rule, because))
    dropped = 0
    while len(existing) > MAX_LESSONS:
        existing.pop(0)
        dropped += 1

    _write(role_key, existing)
    note = f" Вытеснено самых старых: {dropped}." if dropped else ""
    return f"Урок записан ({len(existing)} из {MAX_LESSONS}).{note}"


def _write(role_key: str, lessons: list[Lesson]) -> None:
    role = config.get_role(role_key)
    lines = [
        f"# Уроки роли «{role.title}»",
        "",
        "Записывается только после поправки человека. Подмешивается в промпт",
        "при каждом запуске — поэтому здесь короткие правила, а не история.",
        "",
    ]
    for lesson in lessons:
        lines.append(f"- **{lesson.date}** {lesson.rule}")
        lines.append(f"  _причина:_ {lesson.because}")
    Workspace(role_key).write(LESSONS_PATH, "\n".join(lines) + "\n")


def for_prompt(role_key: str) -> str:
    """Блок для системного промпта. Пустой, пока уроков нет."""
    lessons = load(role_key)
    if not lessons:
        return ""
    body = "\n".join(f"- {l.rule}  _({l.because})_" for l in lessons)
    return (
        "## Твои уроки\n\n"
        "Это поправки, которые человек делал тебе раньше. Каждая записана "
        "после того, как ты ошибся. Они важнее общих правил ниже: там сказано, "
        "как работать вообще, а здесь — как работать с этим человеком.\n\n"
        f"{body}\n"
    )


def export(role_key: str) -> str:
    """Уроки одной строкой JSON — чтобы перенести на другую машину."""
    return json.dumps([asdict(l) for l in load(role_key)], ensure_ascii=False)
