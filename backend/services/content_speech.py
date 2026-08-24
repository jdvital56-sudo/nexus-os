"""Разбор голосовой команды контент-завода: тема, дата публикации, площадки.

Фаундер формулирует это одной фразой: «создай контент на тему X на 27
августа, выставь на инстаграм и тикток». Разбираем правилами, а не
моделью: команда должна срабатывать мгновенно и одинаково, а не зависеть
от настроения LLM и её бюджета — тот же подход, что у _try_open/_try_task
в conversation.py.

Дата и площадки необязательны: без них команда работает как раньше и
просто создаёт черновики без расписания.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Час по умолчанию, когда фаундер назвал день, но не назвал время.
# Полночь не годится: напоминание в 00:00 он увидит только утром.
DEFAULT_HOUR = 10

_COMMAND = re.compile(
    r"^\s*(?:создай|сделай|запусти)\s+(?:мне\s+)?контент[- ]?(?:план)?\b(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)

# Тема идёт после «на тему» / «про» / «о» — либо сразу после слова «контент».
_TOPIC_LEAD = re.compile(r"^\s*(?:на\s+тему|про|об?)\s+", re.IGNORECASE)

_MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}

_WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "сред": 2, "четверг": 3,
    "пятниц": 4, "суббот": 5, "воскресень": 6,
}

# Площадки — намерение фаундера, не интеграция: система никуда не
# публикует, она только помнит, куда он собирался (решение 23.08.2026).
_PLATFORMS = {
    "instagram": ("инстаграм", "инста", "instagram"),
    "tiktok": ("тикток", "тик-ток", "tiktok"),
    "youtube": ("ютуб", "youtube", "шортс"),
    "facebook": ("фейсбук", "facebook", "фб"),
    "telegram": ("телеграм", "телега", "telegram"),
    "linkedin": ("линкедин", "linkedin"),
    "x": ("твиттер", "twitter"),
}

_DAY_MONTH = re.compile(
    r"\b(?P<day>\d{1,2})\s*(?:-?[ег]о)?\s+(?P<month>[а-яё]{3,})", re.IGNORECASE
)
_TIME = re.compile(r"\bв\s+(?P<hour>\d{1,2})(?:[:.](?P<minute>\d{2}))?\b", re.IGNORECASE)
_PLATFORM_LEAD = re.compile(
    r"\b(?:выставь|выложи|опубликуй|запость|постим?)\b.*$", re.IGNORECASE | re.DOTALL
)


@dataclass
class ContentCommand:
    topic: str
    when: datetime | None = None
    platforms: list[str] = field(default_factory=list)


def _match_month(word: str) -> int | None:
    word = word.lower()
    # «мая» и «март» начинаются одинаково на «ма» — сначала длинные корни
    for stem in sorted(_MONTHS, key=len, reverse=True):
        if word.startswith(stem):
            return _MONTHS[stem]
    return None


def _extract_platforms(text: str) -> tuple[list[str], str]:
    """Достаёт площадки и вырезает их из текста, чтобы не попали в тему."""
    found: list[str] = []
    lowered = text.lower()
    for canonical, aliases in _PLATFORMS.items():
        if any(alias in lowered for alias in aliases):
            found.append(canonical)

    # Вырезаем хвост «выставь на ...», а если такого оборота не было —
    # сами названия площадок, где бы они ни стояли.
    cleaned = _PLATFORM_LEAD.sub("", text)
    if cleaned == text:
        for aliases in _PLATFORMS.values():
            for alias in aliases:
                cleaned = re.sub(rf"\b{re.escape(alias)}\b", "", cleaned, flags=re.IGNORECASE)
    return found, cleaned


def _extract_time(text: str) -> tuple[int | None, int, str]:
    match = _TIME.search(text)
    if not match:
        return None, 0, text
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    if hour > 23 or minute > 59:
        return None, 0, text
    return hour, minute, text[: match.start()] + text[match.end():]


def _extract_date(text: str, now: datetime) -> tuple[datetime | None, str]:
    """Ищет день публикации. Возвращает дату (без времени) и остаток текста."""
    lowered = text.lower()

    for word, delta in (("послезавтра", 2), ("завтра", 1), ("сегодня", 0)):
        if word in lowered:
            cut = re.sub(rf"\b(?:на\s+)?{word}\b", "", text, flags=re.IGNORECASE)
            return now + timedelta(days=delta), cut

    match = _DAY_MONTH.search(text)
    if match:
        month = _match_month(match.group("month"))
        if month:
            day = int(match.group("day"))
            year = now.year
            try:
                when = now.replace(year=year, month=month, day=day)
            except ValueError:
                return None, text
            # «на 3 января», сказанное в августе, — это следующий год
            if when.date() < now.date():
                when = when.replace(year=year + 1)
            # Предлог «на» перед датой остался бы висеть в теме
            before = re.sub(r"\bна\s*$", "", text[: match.start()], flags=re.IGNORECASE)
            return when, before + text[match.end():]

    for word, index in _WEEKDAYS.items():
        found = re.search(rf"\b(?:на\s+|в\s+)?({word}[а-яё]*)\b", lowered)
        if found:
            ahead = (index - now.weekday()) % 7
            ahead = ahead or 7  # «на понедельник» в понедельник — следующий
            cut = text[: found.start()] + text[found.end():]
            return now + timedelta(days=ahead), cut

    return None, text


def parse_command(text: str, now: datetime | None = None) -> ContentCommand | None:
    """Разбирает фразу. Не команда контент-завода — возвращает None."""
    match = _COMMAND.match(text or "")
    if not match:
        return None

    now = now or datetime.now(timezone.utc)
    rest = match.group("rest")

    platforms, rest = _extract_platforms(rest)
    hour, minute, rest = _extract_time(rest)
    after_date, without_date = _extract_date(rest, now)

    # Дата могла оказаться самой темой: «создай контент про пятницу» — это
    # контент О пятнице, а не контент НА пятницу. Признак — от темы после
    # выреза не осталось ничего, кроме служебного предлога. Тогда откат:
    # считаем, что даты в команде не было (найдено живым прогоном 23.08.2026,
    # тот прогон дал topic='про', when=пятница). Тот же принцип, что у
    # _try_open в conversation.py: перехватываем только когда действительно
    # распознали цель, иначе не выдумываем.
    day = after_date
    rest_for_topic = without_date
    if day is not None and not _clean_topic(without_date):
        day = None
        rest_for_topic = rest

    when = None
    if day is not None:
        when = day.replace(
            hour=hour if hour is not None else DEFAULT_HOUR,
            minute=minute,
            second=0,
            microsecond=0,
        )

    return ContentCommand(topic=_clean_topic(rest_for_topic), when=when, platforms=platforms)


def _clean_topic(text: str) -> str:
    """Убирает ведущий предлог и мусорные символы. Пустая строка означает,
    что темы в этом куске нет вовсе."""
    topic = _TOPIC_LEAD.sub("", text.strip())
    topic = re.sub(r"\s+", " ", topic).strip(" ,.!?-—:")
    # Одинокий предлог темой не считается: «про» осталось от «про пятницу»
    if topic.lower() in ("про", "о", "об", "на тему", "тему", "на"):
        return ""
    return topic
