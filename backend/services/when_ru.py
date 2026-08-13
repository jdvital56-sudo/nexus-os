"""Разбор времени из живой русской речи.

Фаундер говорит голосом: «поставь встречу в четверг в 15:00», «завтра в
девять», «через час созвон». Модель для этого звать незачем — это разбор
текста, он должен быть мгновенным, бесплатным и одинаковым каждый раз.

Возвращаем не только время, но и остаток фразы: из «встреча с Ольгой
завтра в 15:00» нужно достать и «встреча с Ольгой», и саму дату.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "среду": 2, "среда": 2, "четверг": 3,
    "пятницу": 4, "пятница": 4, "субботу": 5, "суббота": 5,
    "воскресенье": 6, "понедельника": 0, "вторника": 1, "четверга": 3,
}

MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

# Числа словами — в речи «в девять» звучит чаще, чем «в 9»
WORD_HOURS = {
    "час": 1, "два": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6,
    "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "одиннадцать": 11,
    "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15,
    "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19,
    "двадцать": 20,
}

# Если человек сказал «в 3», он почти наверняка имеет в виду день, а не ночь
DAY_START_HOUR = 8

# Встреча по умолчанию — час: столько длится обычный разговор
DEFAULT_DURATION = 60


@dataclass
class Moment:
    start: datetime
    duration_minutes: int
    text: str          # что осталось от фразы — название события
    explicit_time: bool  # время названо явно или подставлено по умолчанию


def _strip(text: str, *fragments: str) -> str:
    for fragment in fragments:
        if fragment:
            text = text.replace(fragment, " ")
    return re.sub(r"\s{2,}", " ", text).strip(" ,.—-")


def parse(phrase: str, now: datetime | None = None) -> Moment | None:
    """Достаёт из фразы дату, время и название. None — если времени нет."""
    now = now or datetime.now()
    lowered = phrase.lower()

    date_part: datetime | None = None
    consumed: list[str] = []

    # «через час», «через 20 минут» — считаем от текущего момента
    relative = re.search(r"через\s+(\d+|час|полчаса)\s*(минут\w*|час\w*)?", lowered)
    if relative:
        amount, unit = relative.group(1), relative.group(2) or ""
        if amount == "полчаса":
            delta = timedelta(minutes=30)
        elif amount == "час":
            delta = timedelta(hours=1)
        elif unit.startswith("мин"):
            delta = timedelta(minutes=int(amount))
        else:
            delta = timedelta(hours=int(amount))
        return Moment(
            start=(now + delta).replace(second=0, microsecond=0),
            duration_minutes=DEFAULT_DURATION,
            text=_strip(phrase, relative.group(0)),
            explicit_time=True,
        )

    # «сегодня», «завтра», «послезавтра»
    for word, shift in (("послезавтра", 2), ("завтра", 1), ("сегодня", 0)):
        if word in lowered:
            date_part = now + timedelta(days=shift)
            consumed.append(word)
            break

    # «в четверг» — ближайший будущий, «в следующий четверг» — плюс неделя
    if date_part is None:
        for name, index in WEEKDAYS.items():
            # Предлог съедаем вместе с днём: иначе в названии остаётся
            # висячее «в» — «созвон в» вместо «созвон»
            found = re.search(rf"\b(?:(?:в|во)\s+)?(?:следующ\w+\s+)?{name}\b", lowered)
            if found:
                ahead = (index - now.weekday()) % 7
                if ahead == 0:
                    ahead = 7  # «в понедельник» в понедельник — это следующий
                if "следующ" in lowered:
                    ahead += 7
                date_part = now + timedelta(days=ahead)
                consumed.append(found.group(0))
                break

    # «25 августа»
    if date_part is None:
        by_month = re.search(r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")\b", lowered)
        if by_month:
            day, month = int(by_month.group(1)), MONTHS[by_month.group(2)]
            year = now.year + (1 if (month, day) < (now.month, now.day) else 0)
            date_part = now.replace(year=year, month=month, day=day)
            consumed.append(by_month.group(0))

    # Время: «в 15:00», «в 15», «в девять», «в 9 утра/вечера»
    hour = minute = None
    explicit = False

    numeric = re.search(r"(?:в|к)\s+(\d{1,2})(?:[:.](\d{2}))?\s*(утра|дня|вечера|ночи)?", lowered)
    worded = re.search(r"(?:в|к)\s+(" + "|".join(WORD_HOURS) + r")\s*(утра|дня|вечера|ночи)?", lowered)

    if numeric:
        hour, minute = int(numeric.group(1)), int(numeric.group(2) or 0)
        part = numeric.group(3)
        consumed.append(numeric.group(0))
        explicit = True
    elif worded:
        hour, minute = WORD_HOURS[worded.group(1)], 0
        part = worded.group(2)
        consumed.append(worded.group(0))
        explicit = True
    else:
        part = None

    if hour is not None:
        if part in ("вечера", "дня") and hour < 12:
            hour += 12
        elif part == "ночи" and hour == 12:
            hour = 0
        elif part is None and hour < DAY_START_HOUR:
            # «в три» — это три дня, а не ночи: ночью встреч не назначают
            hour += 12
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            return None

    if date_part is None and hour is None:
        return None

    base = date_part or now
    if hour is None:
        # Дата есть, времени нет: ставим на начало рабочего дня
        start = base.replace(hour=10, minute=0, second=0, microsecond=0)
    else:
        start = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # «в 15:00» без даты и время уже прошло — значит завтра
        if date_part is None and start <= now:
            start += timedelta(days=1)

    return Moment(
        start=start,
        duration_minutes=DEFAULT_DURATION,
        text=_strip(phrase, *consumed),
        explicit_time=explicit,
    )


def human(moment: datetime) -> str:
    """Дата словами — чтобы человек проверил, туда ли поставили."""
    days = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]
    months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]
    return (
        f"в {days[moment.weekday()]}, {moment.day} {months[moment.month - 1]}, "
        f"в {moment.hour:02d}:{moment.minute:02d}"
    )
