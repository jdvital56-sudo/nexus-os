"""Тесты шины событий и контракта §3 (PR-12)."""
import asyncio
import json

import pytest

from backend.core import eventbus
from backend.services import graph as graph_svc
from backend.services import memory as mem_svc
from backend.models.schemas import GraphEdge, GraphNode, NodeType


def collector() -> tuple[list, callable]:
    """Подписчик, складывающий конверты в список."""
    seen: list[dict] = []

    async def sink(envelope: dict) -> None:
        seen.append(envelope)

    return seen, sink


def test_envelope_matches_contract():
    env = eventbus.make_envelope("chat.message", {"a": 1}, eventbus.SOURCE_HERMES)

    assert set(env) == {"v", "type", "ts", "source", "payload"}
    assert env["v"] == 1
    assert env["type"] == "chat.message"
    assert env["source"] == "hermes"
    assert env["payload"] == {"a": 1}
    # ts — ISO-8601 в UTC
    assert env["ts"].endswith("+00:00")


def test_emit_without_subscribers_is_noop():
    eventbus.emit("chat.message", {"x": 1})  # не должно бросить


@pytest.mark.asyncio
async def test_emit_reaches_subscriber():
    seen, sink = collector()
    eventbus.subscribe(sink)

    eventbus.emit(eventbus.CHAT_MESSAGE, {"channel": "web"}, eventbus.SOURCE_WEB)
    await asyncio.sleep(0.05)

    assert len(seen) == 1
    assert seen[0]["type"] == "chat.message"
    assert seen[0]["source"] == "web"


@pytest.mark.asyncio
async def test_emit_works_from_worker_thread():
    """Запись в память идёт через asyncio.to_thread — оттуда emit тоже обязан долетать."""
    seen, sink = collector()
    eventbus.subscribe(sink)
    eventbus.bind_loop(asyncio.get_running_loop())

    await asyncio.to_thread(eventbus.emit, eventbus.MEMORY_FACT_ADDED, {"fact_id": "x"})
    await asyncio.sleep(0.05)

    assert [e["type"] for e in seen] == ["memory.fact_added"]


@pytest.mark.asyncio
async def test_broken_subscriber_does_not_break_caller():
    async def boom(envelope):
        raise RuntimeError("подписчик упал")

    eventbus.subscribe(boom)

    eventbus.emit(eventbus.CHAT_MESSAGE, {"x": 1})
    await asyncio.sleep(0)  # исключение не должно всплыть наружу


# --- События из точек записи ---


@pytest.mark.asyncio
async def test_new_fact_emits_event():
    seen, sink = collector()
    eventbus.subscribe(sink)

    fact = mem_svc.add_fact("Фаундер работает из Одессы", source="telegram:42")
    await asyncio.sleep(0.05)

    assert len(seen) == 1
    payload = seen[0]["payload"]
    assert payload["fact_id"] == fact.id
    assert payload["layer"] == "inbox"
    assert "Одессе" in payload["summary"] or "Одессы" in payload["summary"]
    assert payload["source"] == "telegram:42"


@pytest.mark.asyncio
async def test_graph_node_and_edge_emit_events():
    seen, sink = collector()
    eventbus.subscribe(sink)

    graph_svc.add_node(GraphNode(id="a", label="Первый", node_type=NodeType.CONCEPT))
    graph_svc.add_node(GraphNode(id="b", label="Второй", node_type=NodeType.AGENT))
    graph_svc.add_edge(GraphEdge(source="a", target="b"))
    await asyncio.sleep(0.05)

    types = [e["type"] for e in seen]
    assert types == ["graph.node_added", "graph.node_added", "graph.edge_added"]
    assert seen[0]["payload"] == {"node_id": "a", "kind": "concept", "label": "Первый"}
    assert seen[2]["payload"] == {"src": "a", "dst": "b", "kind": "related"}


@pytest.mark.asyncio
async def test_dialog_emits_chat_messages():
    from backend.services.conversation import ConversationService

    class Stub:
        async def generate_response(self, m, context="", kind="interactive"):
            return "ответ модели"

    seen, sink = collector()
    eventbus.subscribe(sink)
    svc = ConversationService(llm=Stub(), semantic_dedup=False, extract_entities=False)

    await svc.handle("telegram", "42", "привет")
    await svc.drain()
    await asyncio.sleep(0.05)

    chat = [e for e in seen if e["type"] == "chat.message"]
    assert [e["payload"]["role"] for e in chat] == ["user", "assistant"]
    assert chat[0]["source"] == "hermes"
    assert chat[0]["payload"]["channel"] == "telegram"
    assert chat[1]["payload"]["text_preview"] == "ответ модели"


@pytest.mark.asyncio
async def test_web_channel_is_marked_as_web():
    from backend.services.conversation import ConversationService

    class Stub:
        async def generate_response(self, m, context="", kind="interactive"):
            return "ответ"

    seen, sink = collector()
    eventbus.subscribe(sink)
    svc = ConversationService(llm=Stub(), semantic_dedup=False, extract_entities=False)

    await svc.handle("web", "42", "привет")
    await svc.drain()
    await asyncio.sleep(0.05)

    assert [e["source"] for e in seen if e["type"] == "chat.message"] == ["web", "web"]


@pytest.mark.asyncio
async def test_budget_trip_is_visible(monkeypatch):
    """Сработавший предохранитель обязан быть виден в Activity (I-6)."""
    from backend.core.config import settings
    from backend.services import budget

    monkeypatch.setattr(settings, "daily_llm_budget_usd", 0.0)
    seen, sink = collector()
    eventbus.subscribe(sink)

    budget.check(budget.INTERACTIVE)
    await asyncio.sleep(0.05)

    assert seen[0]["type"] == "system.budget"
    assert seen[0]["payload"]["throttled"] is True


# --- Транспорт /ws ---


def live_client():
    """TestClient как контекст-менеджер — иначе startup не выполняется
    и вебсокет не подписывается на шину."""
    from fastapi.testclient import TestClient

    from backend.main import app

    return TestClient(app)


def test_websocket_streams_events_by_contract():
    """DoD PR-12: подключение к /ws показывает поток строго по схеме §3."""
    with live_client() as c, c.websocket_connect("/ws") as ws:
        hello = json.loads(ws.receive_text())
        assert hello["type"] == "connected"
        assert hello["v"] == 1

        mem_svc.add_fact("Событие для вебсокета", source="test")

        event = json.loads(ws.receive_text())
        assert set(event) == {"v", "type", "ts", "source", "payload"}
        assert event["type"] == "memory.fact_added"
        assert event["payload"]["summary"] == "Событие для вебсокета"
        assert event["source"] == "system"


def test_websocket_receives_whole_dialog_stream():
    """Диалог целиком: сообщение, ответ и факт памяти."""
    from backend.services.conversation import ConversationService

    class Stub:
        async def generate_response(self, m, context="", kind="interactive"):
            return "ответ модели"

    with live_client() as c, c.websocket_connect("/ws") as ws:
        ws.receive_text()  # connected

        svc = ConversationService(llm=Stub(), semantic_dedup=False, extract_entities=False)
        asyncio.run(_dialog(svc))

        types = [json.loads(ws.receive_text())["type"] for _ in range(3)]

    assert types == ["chat.message", "chat.message", "memory.fact_added"]


async def _dialog(svc) -> None:
    await svc.handle("telegram", "42", "привет")
    await svc.drain()


def test_websocket_survives_client_disconnect():
    with live_client() as c:
        with c.websocket_connect("/ws") as ws:
            ws.receive_text()

        # Клиент отвалился — запись в память не должна падать
        mem_svc.add_fact("После отключения", source="test")
