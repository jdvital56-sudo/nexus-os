"""WebSocket endpoint for real-time events.

Транспорт поверх шины событий: конверт формирует core.eventbus по
контракту §3, здесь только доставка подключённым клиентам.
"""
import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core import eventbus
from ..core.auth import _load_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])

# Connected clients
_clients: set[WebSocket] = set()


async def _fanout(envelope: dict[str, Any]) -> None:
    """Разослать конверт всем живым клиентам, мёртвых — отцепить."""
    if not _clients:
        return
    message = json.dumps(envelope, ensure_ascii=False)
    dead = set()
    for client in list(_clients):
        try:
            await client.send_text(message)
        except Exception:
            dead.add(client)
    _clients.difference_update(dead)


def install() -> None:
    """Подписать вебсокет на шину. Вызывается при старте приложения."""
    eventbus.subscribe(_fanout)


async def broadcast(event_type: str, payload: dict[str, Any], source: str = eventbus.SOURCE_SYSTEM):
    """Отправить событие напрямую (для кода, который уже в цикле событий)."""
    await _fanout(eventbus.make_envelope(event_type, payload, source))


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None):
    """Токен — в строке запроса (`?token=...`), не в заголовке: браузерный
    WebSocket API не умеет слать Authorization при подключении, тот же
    класс проблемы, что у /api/voice/say-stream (см. его же
    _verify_query_token). Найдено код-ревью 20.08.2026: раньше эта ручка
    вообще не проверяла ничего — кто угодно с сетевым доступом мог
    подключиться и слушать всю ленту событий системы (память, задачи,
    активность агентов) без единого токена.
    """
    stored = _load_token()
    if stored and token != stored:
        await websocket.close(code=1008)  # policy violation
        return

    await websocket.accept()
    _clients.add(websocket)
    try:
        await websocket.send_text(json.dumps(
            eventbus.make_envelope(
                "connected",
                {"message": "Nexus OS event stream connected", "schema": eventbus.SCHEMA_VERSION},
                eventbus.SOURCE_SYSTEM,
            ),
            ensure_ascii=False,
        ))

        # Keep alive and listen for pings
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps(
                    eventbus.make_envelope("heartbeat", {}, eventbus.SOURCE_SYSTEM),
                    ensure_ascii=False,
                ))
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(websocket)


def get_connected_count() -> int:
    return len(_clients)
