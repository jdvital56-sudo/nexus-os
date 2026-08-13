"""Полная лента переписки — то, что человек читает на экране.

Фаундер прислал скрин: длинный ответ обрывался на полуслове. Экран читал
буфер для промпта, а тот режется до 600 символов на реплику.
"""
import pytest

from backend.services import chat_log, dialog_history


def test_long_reply_is_kept_whole():
    long_text = "слово " * 500

    chat_log.append_turn("web", "founder", [("assistant", long_text, "Orpheus")])

    stored = chat_log.recent("web", "founder")[0]["text"]
    assert len(stored) > 600
    assert not stored.endswith("…")


def test_prompt_buffer_still_clips():
    """Буфер для промпта обязан оставаться коротким — он идёт в модель."""
    dialog_history.append_turn("web", "founder", "вопрос", "ответ " * 500, "Orpheus")

    kept = dialog_history.recent("web", "founder")[-1]["text"]
    assert len(kept) <= dialog_history.MAX_CHARS + 1


def test_log_keeps_more_than_the_buffer():
    for i in range(40):
        chat_log.append_turn("web", "founder", [("user", f"сообщение {i}", "")])

    assert len(chat_log.recent("web", "founder", limit=100)) == 40


def test_channels_are_separate():
    chat_log.append_turn("telegram", "42", [("user", "телеграмное", "")])

    assert chat_log.recent("web", "founder") == []


def test_clear_removes_only_one_channel():
    chat_log.append_turn("web", "founder", [("user", "веб", "")])
    chat_log.append_turn("telegram", "42", [("user", "телеграм", "")])

    chat_log.clear("web", "founder")

    assert chat_log.recent("web", "founder") == []
    assert len(chat_log.recent("telegram", "42")) == 1


@pytest.mark.asyncio
async def test_api_history_returns_full_text(client, monkeypatch):
    import backend.api.chat as chat_api

    long_reply = "**жирно** " + "текст " * 300

    class Fake:
        async def handle(self, channel, user_id, text, persona=None):
            chat_log.append_turn(channel, user_id, [("user", text, ""), ("assistant", long_reply, "Orpheus")])
            return long_reply

    monkeypatch.setattr(chat_api, "get_conversation_service", lambda: Fake())
    client.post("/api/chat/message", json={"text": "вопрос"})

    messages = client.get("/api/chat/history").json()["messages"]
    assistant = [m for m in messages if m["role"] == "assistant"][0]

    assert len(assistant["text"]) > 600
    # Разметку на экран не отдаём: в переписке она видна как мусор
    assert "**" not in assistant["text"]
