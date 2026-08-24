"""Разбор голосовой команды контент-завода: тема + дата + площадки.

Фраза фаундера-образец (23.08.2026): «создай мне контент на такую-то тему
на такое-то число, выставь на такие-то площадки». Дата и площадки
необязательны — без них команда работает как раньше, просто черновик
никуда не назначен.
"""
from datetime import datetime, timedelta, timezone

import pytest

from backend.services import content_speech as cs


NOW = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)  # понедельник


def _parse(text: str):
    return cs.parse_command(text, now=NOW)


# === Тема ===

def test_plain_topic_without_date():
    got = _parse("создай контент про утренние ритуалы")
    assert got.topic == "утренние ритуалы"
    assert got.when is None
    assert got.platforms == []


def test_topic_via_na_temu():
    got = _parse("создай контент на тему здоровый сон")
    assert got.topic == "здоровый сон"


def test_not_a_content_command():
    assert _parse("какая сегодня погода") is None


def test_empty_topic():
    got = _parse("создай контент")
    assert got is not None
    assert got.topic == ""


# === Дата ===

def test_tomorrow():
    got = _parse("создай контент про кофе на завтра")
    assert got.topic == "кофе"
    assert got.when.date() == (NOW + timedelta(days=1)).date()


def test_day_after_tomorrow():
    got = _parse("создай контент про кофе на послезавтра")
    assert got.when.date() == (NOW + timedelta(days=2)).date()


def test_explicit_day_and_month():
    got = _parse("создай контент про отпуск на 27 августа")
    assert got.topic == "отпуск"
    assert (got.when.day, got.when.month) == (27, 8)


def test_day_month_rolls_to_next_year_when_past():
    """«на 3 января», сказанное в августе, — это январь следующего года."""
    got = _parse("создай контент про итоги на 3 января")
    assert (got.when.day, got.when.month, got.when.year) == (3, 1, 2027)


def test_weekday_picks_upcoming():
    got = _parse("создай контент про спорт на пятницу")
    assert got.topic == "спорт"
    assert got.when.weekday() == 4  # пятница
    assert got.when > NOW


def test_time_of_day():
    got = _parse("создай контент про кофе на завтра в 18:30")
    assert (got.when.hour, got.when.minute) == (18, 30)


def test_time_without_minutes():
    got = _parse("создай контент про кофе на завтра в 9")
    assert got.when.hour == 9


def test_default_time_is_morning():
    """Без указанного часа ставим утро, а не полночь: напоминание в 00:00
    фаундер увидит только на следующий день."""
    got = _parse("создай контент про кофе на завтра")
    assert got.when.hour == cs.DEFAULT_HOUR


# === Площадки ===

def test_platforms_after_vystavi():
    got = _parse("создай контент про кофе выставь на инстаграм и тикток")
    assert got.topic == "кофе"
    assert set(got.platforms) == {"instagram", "tiktok"}


def test_platforms_latin_names():
    got = _parse("создай контент про кофе на youtube и facebook")
    assert set(got.platforms) == {"youtube", "facebook"}


def test_unknown_platform_ignored():
    got = _parse("создай контент про кофе выставь на мойсайт")
    assert got.platforms == []


def test_full_command():
    got = _parse("создай контент на тему летний отпуск на 27 августа в 12:00 выставь на инстаграм и ютуб")
    assert got.topic == "летний отпуск"
    assert (got.when.day, got.when.month, got.when.hour) == (27, 8, 12)
    assert set(got.platforms) == {"instagram", "youtube"}


def test_platforms_do_not_leak_into_topic():
    got = _parse("создай контент про кофе на завтра выставь на инстаграм")
    assert "инстаграм" not in got.topic
    assert "завтра" not in got.topic


# === Дата, которая на самом деле была темой (найдено живым прогоном 23.08) ===


def test_weekday_as_topic_is_not_eaten_as_a_date():
    """«создай контент ПРО ПЯТНИЦУ» — это тема, а не день публикации.

    Живой прогон дал topic='про', when=пятница: разбор даты срезал слово
    раньше, чем до него добирался разбор темы, и от темы оставался огрызок
    предлога. Пустая/служебная тема — верный признак, что дату вырезали
    зря: откатываемся и считаем это темой.
    """
    got = _parse("создай контент про пятницу")
    assert got.topic == "пятницу"
    assert got.when is None


def test_weekday_still_works_when_topic_survives():
    """Обратный случай: тема есть, значит день недели — настоящая дата."""
    got = _parse("создай контент про спа на пятницу")
    assert got.topic == "спа"
    assert got.when is not None
    assert got.when.weekday() == 4


def test_tomorrow_as_topic_is_not_eaten_either():
    got = _parse("создай контент про завтра")
    assert got.topic == "завтра"
    assert got.when is None


def test_month_day_as_topic_is_not_eaten_either():
    got = _parse("создай контент про 8 марта")
    assert got.topic == "8 марта"
    assert got.when is None


def test_platforms_survive_the_rollback():
    """Откат даты не должен терять уже разобранные площадки."""
    got = _parse("создай контент про пятницу, выставь на инстаграм")
    assert got.topic == "пятницу"
    assert got.when is None
    assert got.platforms == ["instagram"]
