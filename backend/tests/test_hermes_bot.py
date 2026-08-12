"""Тесты Гермеса — боевого канала связи с системой.

До них это был единственный крупный файл без покрытия, и при этом
единственный, через который фаундер вообще разговаривает с Nexus OS.
Сеть здесь не нужна: объекты Telegram подменяются, а разговор — заглушкой.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from hermes.bot import HermesAgent, strip_markdown


@pytest.fixture
def agent():
    """Агент без конструктора.

    Настоящий __init__ поднимает LLM, Apollo, календарь и разговор — всё
    это лезет в сеть и к ключам. Нам нужны методы, а не окружение.
    """
    bot = object.__new__(HermesAgent)
    bot.allowed_user_id = ""
    bot.conversation = SimpleNamespace(handle=AsyncMock(return_value="ответ"))
    return bot


def _update(user_id=777, text="привет"):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, username="founder"),
        message=SimpleNamespace(text=text, reply_text=AsyncMock()),
    )


# === Разметка ===


@pytest.mark.parametrize("raw,clean", [
    ("**жирный**", "жирный"),
    ("__жирный__", "жирный"),
    ("# Заголовок", "Заголовок"),
    ("### Третий уровень", "Третий уровень"),
    ("`код`", "код"),
    ("```блок```", "блок"),
    ("* пункт", "- пункт"),
    ("+ пункт", "- пункт"),
])
def test_markdown_is_stripped(raw, clean):
    assert strip_markdown(raw) == clean


def test_plain_text_is_untouched():
    text = "Ставка по офферу — 60 тысяч. Позвонить в 15:00."
    assert strip_markdown(text) == text


def test_multiplication_is_not_treated_as_markup():
    """Звёздочка между словами — не разметка, а умножение."""
    assert strip_markdown("2 * 3 = 6") == "2 * 3 = 6"


def test_markup_across_lines():
    assert strip_markdown("**первая\nвторая**") == "первая\nвторая"


def test_empty_input():
    assert strip_markdown("") == ""


# === Авторизация ===


def test_without_restriction_everyone_passes(agent):
    agent.allowed_user_id = ""
    assert agent._authorize_user(12345) is True


def test_only_the_owner_passes(agent):
    agent.allowed_user_id = "777"
    assert agent._authorize_user(777) is True
    assert agent._authorize_user(778) is False


def test_id_compared_as_text_not_number(agent):
    """Telegram отдаёт число, в настройках лежит строка."""
    agent.allowed_user_id = "777"
    assert agent._authorize_user(777) is True


def test_refusal_is_logged(agent, caplog):
    """Молчание бота и его поломка обязаны различаться в логах."""
    agent.allowed_user_id = "777"
    with caplog.at_level("WARNING"):
        agent._authorize_user(999)
    assert "999" in caplog.text


def test_owner_id_is_not_logged_on_success(agent, caplog):
    agent.allowed_user_id = "777"
    with caplog.at_level("WARNING"):
        agent._authorize_user(777)
    assert caplog.text == ""


# === Обработка сообщений ===


@pytest.mark.asyncio
async def test_message_reaches_the_conversation(agent):
    update = _update(text="какая ставка")
    await agent.handle_message(update, None)

    agent.conversation.handle.assert_awaited_once()
    kwargs = agent.conversation.handle.await_args.kwargs
    assert kwargs["text"] == "какая ставка"
    assert kwargs["channel"] == "telegram"
    update.message.reply_text.assert_awaited_once_with("ответ")


@pytest.mark.asyncio
async def test_stranger_gets_no_reply(agent):
    agent.allowed_user_id = "777"
    update = _update(user_id=999)

    await agent.handle_message(update, None)

    agent.conversation.handle.assert_not_awaited()
    update.message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_reply_is_cleaned_of_markup(agent):
    agent.conversation.handle = AsyncMock(return_value="**Ставка** — 60 тысяч")
    update = _update()

    await agent.handle_message(update, None)

    update.message.reply_text.assert_awaited_once_with("Ставка — 60 тысяч")


@pytest.mark.asyncio
async def test_failure_does_not_leave_the_user_in_silence(agent):
    """Молчащий бот неотличим от сломанного — ошибка обязана быть видна."""
    agent.conversation.handle = AsyncMock(side_effect=RuntimeError("модель упала"))
    update = _update()

    await agent.handle_message(update, None)

    update.message.reply_text.assert_awaited_once()
    assert "ошибка" in update.message.reply_text.await_args.args[0].lower()


HANDLERS = [
    "start_command", "help_command", "status_command", "persons_command",
    "brief_command", "reset_command", "services_command",
    "handle_message", "handle_voice",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", HANDLERS)
async def test_every_handler_refuses_strangers(agent, handler):
    """Ни одна команда не должна отвечать чужому.

    Проверяем поимённо: заслон легко забыть в новой команде, и заметить
    это по одному тесту на handle_message невозможно.
    """
    agent.allowed_user_id = "777"
    update = _update(user_id=999)

    await getattr(agent, handler)(update, None)

    update.message.reply_text.assert_not_awaited()


def test_no_handler_is_left_without_the_guard():
    """Сторож на уровне исходника: новая команда без заслона уронит тест."""
    import inspect

    import hermes.bot as bot_module

    source = inspect.getsource(bot_module)
    handlers = [line for line in source.splitlines() if "async def " in line and
                ("_command" in line or "handle_" in line)]
    assert len(handlers) == len(HANDLERS), (
        f"обработчиков стало {len(handlers)}, а в списке проверки {len(HANDLERS)} — "
        "добавь новый в HANDLERS и убедись, что в нём есть _authorize_user"
    )


@pytest.mark.asyncio
async def test_internal_error_text_is_not_shown_to_the_user(agent):
    agent.conversation.handle = AsyncMock(side_effect=RuntimeError("ключ sk-secret недействителен"))
    update = _update()

    await agent.handle_message(update, None)

    shown = update.message.reply_text.await_args.args[0]
    assert "sk-secret" not in shown
