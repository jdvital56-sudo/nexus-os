"""Разбор времени из живой речи: «поставь встречу в четверг в 15:00».

Модель для этого не зовём — разбор обязан быть мгновенным, бесплатным и
одинаковым каждый раз. Поэтому проверок много: ошибка здесь ставит встречу
не в тот день, а человек узнаёт об этом, когда её пропустит.
"""
from datetime import datetime

import pytest

from backend.services import when_ru

# Среда, 12 августа 2026, 10:00 — от неё считаем всё
NOW = datetime(2026, 8, 12, 10, 0)


def parse(text: str):
    return when_ru.parse(text, now=NOW)


def test_tomorrow_with_time():
    m = parse("встреча с Ольгой завтра в 15:00")

    assert (m.start.day, m.start.hour, m.start.minute) == (13, 15, 0)
    assert m.text == "встреча с Ольгой"


def test_weekday_takes_the_next_one():
    m = parse("созвон в четверг в 9:30")

    assert (m.start.day, m.start.hour, m.start.minute) == (13, 9, 30)
    assert m.text == "созвон"


def test_same_weekday_means_next_week():
    """«В среду» в среду — это следующая среда, а не сегодня."""
    m = parse("в среду в 11")

    assert m.start.day == 19


def test_next_weekday_adds_a_week():
    m = parse("в следующий четверг в 15")

    assert m.start.day == 20


def test_hours_in_words():
    m = parse("завтра в девять утра планёрка")

    assert (m.start.hour, m.start.minute) == (9, 0)
    assert "планёрка" in m.text


def test_evening_shifts_to_pm():
    m = parse("сегодня в 7 вечера")

    assert m.start.hour == 19


def test_small_hour_without_part_means_daytime():
    """«В три» — это три дня: ночью встреч не назначают."""
    m = parse("завтра в 3")

    assert m.start.hour == 15


def test_time_without_date_moves_to_tomorrow_if_passed():
    m = parse("в 9:00 звонок")

    assert m.start.day == 13
    assert m.start.hour == 9


def test_time_without_date_stays_today_if_ahead():
    m = parse("в 18:00 ужин")

    assert (m.start.day, m.start.hour) == (12, 18)


def test_relative_hours():
    m = parse("через 2 часа забрать документы")

    assert (m.start.hour, m.start.minute) == (12, 0)
    assert "забрать документы" in m.text


def test_relative_minutes():
    m = parse("через 20 минут выйти")

    assert (m.start.hour, m.start.minute) == (10, 20)


def test_half_an_hour():
    m = parse("через полчаса перерыв")

    assert (m.start.hour, m.start.minute) == (10, 30)


def test_explicit_date_by_month():
    m = parse("25 августа в 14:00 конференция")

    assert (m.start.month, m.start.day, m.start.hour) == (8, 25, 14)


def test_past_date_by_month_rolls_to_next_year():
    m = parse("3 марта в 12:00")

    assert (m.start.year, m.start.month, m.start.day) == (2027, 3, 3)


def test_date_without_time_starts_the_workday():
    m = parse("завтра встреча с подрядчиком")

    assert (m.start.day, m.start.hour) == (13, 10)
    assert m.explicit_time is False


def test_phrase_without_time_is_not_a_moment():
    assert parse("расскажи, что у меня по задачам") is None


def test_absurd_time_is_refused():
    assert parse("в 99:00 встреча") is None


def test_human_reads_like_speech():
    m = parse("завтра в 15:00")

    assert when_ru.human(m.start) == "в четверг, 13 августа, в 15:00"


@pytest.mark.parametrize(
    "phrase,hour",
    [("в 8 утра", 8), ("в 8 вечера", 20), ("в 12 дня", 12), ("в 12 ночи", 0)],
)
def test_parts_of_day(phrase, hour):
    assert parse(phrase).start.hour == hour
