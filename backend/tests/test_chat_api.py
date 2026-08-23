"""Веб-чат — второй вход в тот же контур мышления (PR-23).

Главное, что проверяют эти тесты: веб-чат не заводит второй мозг. Он зовёт
тот же ConversationService, что и Телеграм, поэтому память и персоны у них
общие, а нить разговора — раздельная.
"""
import json

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

    async def handle_stream(self, channel: str, user_id: str, text: str, persona: str | None = None):
        self.calls.append({"channel": channel, "user_id": user_id, "text": text, "persona": persona})
        dialog_history.append_turn(channel, user_id, text, self.reply, persona or "Orpheus")
        chat_log.append_turn(
            channel, user_id, [("user", text, ""), ("assistant", self.reply, persona or "Orpheus")]
        )
        # Режем на два куска — проверяем, что эндпоинт реально отдаёт по
        # частям, а не собирает всё обратно в один блок
        half = max(1, len(self.reply) // 2)
        yield self.reply[:half]
        yield self.reply[half:]


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


# --- /api/chat/stream: 23.08.2026, тот же ответ, но по кускам (SSE) ---


def _sse_events(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def test_stream_delivers_reply_in_pieces(client, fake):
    r = client.post("/api/chat/stream", json={"text": "привет"})

    assert r.status_code == 200
    events = _sse_events(r.text)
    deltas = [e["delta"] for e in events if "delta" in e]
    assert len(deltas) == 2  # FakeConversation.handle_stream режет на два куска
    assert "".join(deltas) == "ответ из веба"


def test_stream_ends_with_done_and_persona(client, fake):
    r = client.post("/api/chat/stream", json={"text": "привет", "persona": "Architect"})

    events = _sse_events(r.text)
    assert events[-1] == {"done": True, "persona": "Architect"}


def test_stream_uses_the_same_brain_and_channel(client, fake):
    client.post("/api/chat/stream", json={"text": "вопрос по потоку"})

    assert fake.calls[0]["channel"] == "web"
    assert fake.calls[0]["text"] == "вопрос по потоку"


def test_stream_empty_message_is_refused(client, fake):
    assert client.post("/api/chat/stream", json={"text": "   "}).status_code == 400
    assert fake.calls == []


def test_stream_writes_to_the_same_history_as_message(client, fake):
    """Стриминговый и обычный путь пишут в одну и ту же ленту — иначе
    история в чате будет неполной в зависимости от того, каким путём
    пришёл ответ."""
    client.post("/api/chat/stream", json={"text": "через поток"})

    messages = client.get("/api/chat/history").json()["messages"]
    assert [m["text"] for m in messages if m["role"] == "user"] == ["через поток"]


def test_stream_broken_brain_reports_error_event(client, monkeypatch):
    import backend.api.chat as chat_api

    class Broken:
        async def handle_stream(self, **kwargs):
            raise RuntimeError("модель недоступна")
            yield  # делает функцию генератором, до этой строки не дойдёт

    monkeypatch.setattr(chat_api, "get_conversation_service", lambda: Broken())

    r = client.post("/api/chat/stream", json={"text": "привет"})

    events = _sse_events(r.text)
    assert any("модель недоступна" in e.get("error", "") for e in events)
