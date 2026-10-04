"""Уроки роли — механизм, которым агент отличается от себя вчерашнего.

Проверяется и то, что урок доезжает до промпта, и то, что файл не может
распухнуть или наполниться мусором: без второго «обучение» превращается в
свод правил, которого никто не устанавливал.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from crew import config, lessons
from crew.runner import Runner


@pytest.fixture(autouse=True)
def crew_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CREW_ROOT", tmp_path / "crew")
    config.ensure_layout()


# --- что должно работать ---------------------------------------------------

def test_lesson_is_saved_and_read_back():
    lessons.add("marketer", "Средний чек без источника помечать гипотезой", "выдал догадку за факт")
    saved = lessons.load("marketer")
    assert len(saved) == 1
    assert "гипотезой" in saved[0].rule
    assert saved[0].because == "выдал догадку за факт"


def test_lesson_reaches_the_system_prompt():
    """Смысл всего механизма: урок обязан оказаться в промпте следующего запуска."""
    lessons.add("marketer", "Всегда указывать, какие страницы проверил", "утверждал отсутствие вслепую")
    prompt = Runner("marketer", "c").system_prompt()
    assert "какие страницы проверил" in prompt
    assert "Твои уроки" in prompt


def test_lessons_are_placed_after_the_role_text():
    """Ближе к концу промпта модель соблюдает написанное лучше."""
    lessons.add("marketer", "Правило-маркер", "причина")
    prompt = Runner("marketer", "c").system_prompt()
    assert prompt.index("Правило-маркер") > prompt.index("# Маркетолог")


def test_prompt_has_no_lessons_block_when_there_are_none():
    prompt = Runner("screenwriter", "c").system_prompt()
    assert "Твои уроки" not in prompt


def test_lessons_are_isolated_per_role():
    lessons.add("marketer", "Правило Маркетолога", "причина")
    assert lessons.load("screenwriter") == []
    assert "Правило Маркетолога" not in Runner("screenwriter", "c").system_prompt()


# --- что должно ПО-ПРЕЖНЕМУ не работать ------------------------------------

def test_lesson_without_reason_is_refused():
    """Правило без причины через месяц выглядит произволом, и его нарушат."""
    with pytest.raises(lessons.LessonError):
        lessons.add("marketer", "Делай хорошо", "")


def test_empty_rule_is_refused():
    with pytest.raises(lessons.LessonError):
        lessons.add("marketer", "   ", "причина")


def test_overlong_lesson_is_refused():
    """Урок — это фраза, которую можно выполнить, а не пересказ разговора."""
    with pytest.raises(lessons.LessonError, match="длиннее"):
        lessons.add("marketer", "и " * 200, "причина")


def test_duplicate_lesson_is_not_added_twice():
    lessons.add("marketer", "Одно и то же правило", "причина")
    result = lessons.add("marketer", "  ОДНО И ТО ЖЕ ПРАВИЛО  ", "другая причина")
    assert "дубль" in result.lower()
    assert len(lessons.load("marketer")) == 1


def test_file_cannot_grow_past_the_cap():
    """Без потолка уроки вытеснят из промпта саму роль."""
    for index in range(lessons.MAX_LESSONS + 12):
        lessons.add("marketer", f"Правило номер {index}", "причина")

    saved = lessons.load("marketer")
    assert len(saved) == lessons.MAX_LESSONS
    # Вытесняется самый старый, свежие сохраняются.
    assert saved[-1].rule.endswith(str(lessons.MAX_LESSONS + 11))
    assert not any(l.rule.endswith(" 0") for l in saved)


def test_lessons_block_stays_small_enough_to_be_followed():
    """Тридцать уроков не должны раздуть промпт до нечитаемого."""
    for index in range(lessons.MAX_LESSONS):
        lessons.add("marketer", f"Правило {index} " + "х" * 250, "причина")
    block = lessons.for_prompt("marketer")
    assert len(block) < 12_000, f"блок уроков разросся до {len(block)} символов"


# --- горячая перезагрузка промптов ----------------------------------------

def test_edited_prompt_takes_effect_without_restart(tmp_path, monkeypatch):
    """Правка промпта должна подхватываться живым ботом.

    Обычный кэш «навсегда» здесь ловушка: фаундер правит файл, бот продолжает
    работать на старом тексте, и правка выглядит как «ничего не изменилось».
    У этого проекта такое уже было с Electron-виджетом на старом фронтенде.
    """
    import time
    from crew import prompts

    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    (roles_dir / "_common.md").write_text("общая часть", encoding="utf-8")
    (roles_dir / "marketer.md").write_text("ПЕРВАЯ ВЕРСИЯ", encoding="utf-8")
    monkeypatch.setattr(prompts, "ROLES_DIR", roles_dir)
    prompts.reload()

    assert "ПЕРВАЯ ВЕРСИЯ" in prompts.load("marketer")

    time.sleep(0.01)
    (roles_dir / "marketer.md").write_text("ВТОРАЯ ВЕРСИЯ", encoding="utf-8")

    text = prompts.load("marketer")
    assert "ВТОРАЯ ВЕРСИЯ" in text, "промпт не перечитался после правки файла"
    assert "ПЕРВАЯ ВЕРСИЯ" not in text


def test_unchanged_prompt_is_not_reread_from_disk(tmp_path, monkeypatch):
    """Обратная сторона: без правок файл не читается заново на каждый запрос."""
    from crew import prompts

    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    (roles_dir / "_common.md").write_text("общая", encoding="utf-8")
    target = roles_dir / "marketer.md"
    target.write_text("текст", encoding="utf-8")
    monkeypatch.setattr(prompts, "ROLES_DIR", roles_dir)
    prompts.reload()

    prompts.load("marketer")
    reads = {"n": 0}
    original = Path.read_text

    def counting(self, *args, **kwargs):
        if self.name == "marketer.md":
            reads["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting)
    for _ in range(5):
        prompts.load("marketer")
    assert reads["n"] == 0, "файл перечитывается, хотя не менялся"


# --- сетка долей: модели плохо считают, считает код -----------------------

def test_beat_grid_confirms_cuts_that_are_on_beat():
    from crew.tools import beat_grid

    period = 60 / 72
    result = beat_grid(72, [period, 2 * period, 4 * period])
    assert result["on_beat"] == 3


def test_beat_grid_catches_cuts_that_are_not_on_beat():
    """Случай, на котором Звукорежиссёр выдал ложное «ложатся точно».

    Склейки через ровные три секунды при 72 BPM: как есть — ни одной на доле.
    Независимая проверка поймала, что модель «пересчитала» сетку, скопировав
    старые числа. Здесь то же самое посчитано кодом.
    """
    from crew.tools import beat_grid

    result = beat_grid(72, [3, 6, 9, 13, 16, 19])
    assert result["on_beat"] == 0
    best_hits = sum(abs(r["delta"]) <= 0.08 for r in result["best_rows"])
    assert best_hits < 6, "одним сдвигом такие склейки не совместить — и это надо сказать честно"


def test_beat_grid_suggests_a_tempo_that_actually_fits():
    """Предложенный темп обязан реально давать больше попаданий, а не выглядеть правдоподобно."""
    from crew.tools import beat_grid

    cuts = [3, 6, 9, 13, 16, 19]
    best = beat_grid(72, cuts)["tempo_options"][0]
    period = 60 / best["bpm"]
    hits = sum(
        abs(c - (best["offset"] + round((c - best["offset"]) / period) * period)) <= 0.08
        for c in cuts
    )
    assert hits == best["hits"] and hits >= 4


def test_beat_grid_refuses_zero_tempo():
    from crew.tools import beat_grid

    with pytest.raises(ValueError):
        beat_grid(0, [1, 2])
