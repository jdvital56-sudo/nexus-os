"""Веб-чат — второй вход в тот же контур мышления (PR-23).

Главное, что проверяют эти тесты: веб-чат не заводит второй мозг. Он зовёт
тот же ConversationService, что и Телеграм, поэтому память и персоны у них
общие, а нить разговора — раздельная.
"""
import pytest

from backend.services import chat_log, dialog_history


class FakeConversation:
    """Подменяет контур мышления: тесты не должны ходить в модель за деньги."""

    def __init__(self, reply: str = "ответ из веба"):
        self.reply = reply
        self.calls: list[dict] = []

    async def handle(self, channel: str, user_id: str, text: str, persona: str | None = None):
        self.calls.append({"channel": channel, "user_id": user_id, "text": text, "persona": persona})
        # Настоящий контур пишет в оба места: короткий буфер для промпта и
        # полную ленту для экрана
        dialog_history.append_turn(channel, user_id, text, self.reply, persona or "Orpheus")
        chat_log.append_turn(
            channel, user_id, [("user", text, ""), ("assistant", self.reply, persona or "Orpheus")]
        )
        return self.reply


@pytest.fixture
def fake(monkeypatch):
    import backend.api.chat as chat_api

    service = FakeConversation()
    monkeypatch.setattr(chat_api, "get_conversation_service", lambda: service)
    return service


def test_message_returns_reply_and_persona(client, fake):
    r = client.post("/api/chat/message", json={"text": "привет"})

    assert r.status_code == 200
    assert r.json()["reply"] == "ответ из веба"
    assert r.json()["persona"] == "Orpheus"


def test_web_chat_uses_the_same_brain(client, fake):
    """Не второй мозг, а второй вход: тот же сервис, канал web (I-1)."""
    client.post("/api/chat/message", json={"text": "вопрос"})

    assert fake.calls[0]["channel"] == "web"
    assert fake.calls[0]["text"] == "вопрос"


def test_persona_can_be_forced(client, fake):
    client.post("/api/chat/message", json={"text": "напиши код", "persona": "Architect"})

    assert fake.calls[0]["persona"] == "Architect"


def test_empty_message_is_refused(client, fake):
    assert client.post("/api/chat/message", json={"text": "   "}).status_code == 400
    assert fake.calls == []


def test_history_returns_the_thread(client, fake):
    client.post("/api/chat/message", json={"text": "первое"})
    client.post("/api/chat/message", json={"text": "второе"})

    messages = client.get("/api/chat/history").json()["messages"]

    assert [m["text"] for m in messages if m["role"] == "user"] == ["первое", "второе"]


def test_thread_is_separate_from_telegram(client, fake):
    """Сказанное в Телеграме не должно всплывать в вебе."""
    chat_log.append_turn("telegram", "42", [("user", "секрет из телеграма", "")])

    messages = client.get("/api/chat/history").json()["messages"]

    assert all("секрет из телеграма" not in m["text"] for m in messages)


def test_reset_clears_only_the_web_thread(client, fake):
    dialog_history.append_turn("telegram", "42", "телеграмное", "ответ")
    chat_log.append_turn("telegram", "42", [("user", "телеграмное", "")])
    client.post("/api/chat/message", json={"text": "веб"})

    removed = client.post("/api/chat/reset").json()["removed"]

    assert removed == 2
    assert client.get("/api/chat/history").json()["messages"] == []
    assert dialog_history.recent("telegram", "42") != []
    assert chat_log.recent("telegram", "42") != []


def test_broken_brain_reports_the_reason(client, monkeypatch):
    """Человек на экране должен видеть причину, а не «что-то пошло не так»."""
    import backend.api.chat as chat_api

    class Broken:
        async def handle(self, **kwargs):
            raise RuntimeError("модель недоступна")

    monkeypatch.setattr(chat_api, "get_conversation_service", lambda: Broken())

    r = client.post("/api/chat/message", json={"text": "привет"})

    assert r.status_code == 502
    assert "модель недоступна" in r.json()["detail"]
