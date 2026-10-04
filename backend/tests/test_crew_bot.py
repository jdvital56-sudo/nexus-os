"""Telegram-слой: доступ, разбиение сообщений, выбор ботов.

Главное здесь — «закрыто по умолчанию». Бот в Telegram доступен всему
интернету по имени, поэтому пустой список разрешённых обязан означать
«никому», а не «всем». Это тот случай, где ошибка в одну строку открывает
файловые инструменты кому угодно.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from crew import bot, config


class FakeUser:
    def __init__(self, user_id: int, username: str = "someone") -> None:
        self.id = user_id
        self.username = username


def make_update(user_id: int | None):
    user = FakeUser(user_id) if user_id is not None else None
    return SimpleNamespace(effective_user=user)


# --- доступ ----------------------------------------------------------------

def test_empty_allowlist_means_nobody_not_everybody(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "")
    assert bot.allowed_users() == set()
    assert bot.is_allowed(make_update(12345)) is False


def test_listed_user_is_allowed(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "42")
    assert bot.is_allowed(make_update(42)) is True


def test_unlisted_user_is_refused(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "42")
    assert bot.is_allowed(make_update(43)) is False


def test_update_without_user_is_refused(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "42")
    assert bot.is_allowed(make_update(None)) is False


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("42", {42}),
        ("42,43", {42, 43}),
        ("42, 43 ; 44", {42, 43, 44}),
        ("42,,43", {42, 43}),
        ("  42  ", {42}),
    ],
)
def test_allowlist_parsing(monkeypatch, raw, expected):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", raw)
    assert bot.allowed_users() == expected


def test_non_numeric_entries_are_dropped_not_crashed(monkeypatch):
    """Username вместо id — частая ошибка при заполнении .env.

    Он не должен ни ронять бота, ни случайно кого-то пропускать: id
    числовой, username подделывается за десять секунд.
    """
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "@vadim, 42")
    assert bot.allowed_users() == {42}


def test_dotenv_is_loaded_by_package_import():
    """Пакет обязан подхватывать .env сам.

    Смоук-проверка при сборке показала: без этого `allowed_users()`
    возвращал пустое множество при заполненном .env — бот молча не отвечал
    бы никому и выглядел бы сломанным без единой ошибки в логе.
    """
    import crew

    assert hasattr(crew, "load_dotenv"), "crew/__init__.py больше не грузит .env"


# --- разбиение длинных ответов --------------------------------------------

def test_short_message_is_not_split():
    assert bot.split_message("коротко") == ["коротко"]


def test_long_message_is_split_and_loses_nothing():
    text = "\n\n".join(f"Абзац номер {i}. " + "слово " * 60 for i in range(40))
    parts = bot.split_message(text)

    assert len(parts) > 1
    assert all(len(p) <= bot.TELEGRAM_LIMIT for p in parts)
    # Содержимое не должно теряться: склейка возвращает исходные абзацы.
    for index in range(40):
        assert f"Абзац номер {index}." in "\n\n".join(parts)


def test_split_does_not_cut_inside_a_word():
    text = "непрерывныйтекстбезпробелов" * 400
    parts = bot.split_message(text)
    assert "".join(parts) == text, "текст без переносов должен склеиваться обратно"


# --- выбор ботов -----------------------------------------------------------

def test_per_role_tokens_win_over_shared(monkeypatch):
    for role in config.ROLES:
        monkeypatch.delenv(role.env_token, raising=False)
    monkeypatch.setenv("CREW_TOKEN_MARKETER", "t1")
    monkeypatch.setenv("CREW_TOKEN_PRODUCER", "t2")
    monkeypatch.setenv("CREW_TOKEN_ALL", "shared")

    pairs = bot.configured_bots()
    assert pairs == [("t1", "marketer"), ("t2", "producer")]


def test_shared_token_serves_whole_crew(monkeypatch):
    for role in config.ROLES:
        monkeypatch.delenv(role.env_token, raising=False)
    monkeypatch.setenv("CREW_TOKEN_ALL", "shared")
    assert bot.configured_bots() == [("shared", None)]


def test_no_tokens_means_no_bots(monkeypatch):
    for role in config.ROLES:
        monkeypatch.delenv(role.env_token, raising=False)
    monkeypatch.delenv("CREW_TOKEN_ALL", raising=False)
    assert bot.configured_bots() == []


def test_every_role_has_a_distinct_token_variable():
    names = [role.env_token for role in config.ROLES]
    assert all(names), "у роли не задано имя переменной с токеном"
    assert len(names) == len(set(names)), "две роли читают один и тот же токен"


# --- логи не должны хранить токены -----------------------------------------

@pytest.fixture
def clean_logging():
    """Сохранить и вернуть состояние логгеров после теста."""
    import logging

    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    saved_levels = {n: logging.getLogger(n).level for n in ("httpx", "httpcore")}
    yield
    root.handlers[:] = saved[0]
    root.setLevel(saved[1])
    for name, level in saved_levels.items():
        logging.getLogger(name).setLevel(level)


def test_httpx_request_urls_with_token_are_not_logged(clean_logging):
    import logging

    # pytest вешает свои обработчики на root уже после фикстур, а при
    # непустом root basicConfig молча ничего не делает — чистим здесь
    logging.getLogger().handlers.clear()
    bot.setup_logging()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
    # и в обратную сторону: свои INFO-строки бот писать не перестал
    assert logging.getLogger("crew.bot").isEnabledFor(logging.INFO)
