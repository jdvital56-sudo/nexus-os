"""WebSocket endpoint for real-time events.

Streams agent activity, graph changes, and pipeline updates.
"""
import asyncio
import json
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Any

router = APIRouter(tags=["events"])

# Connected clients
_clients: set[WebSocket] = set()


async def broadcast(event_type: str, data: dict[str, Any]):
    """Send event to all connected WebSocket clients."""
    message = json.dumps({
        "type": event_type,
        "data": data,
        "timestamp": datetime.utcnow().isoformat(),
    })
    dead = set()
    for client in _clients:
        try:
            await client.send_text(message)
        except Exception:
            dead.add(client)
    _clients.difference_update(dead)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _clients.add(websocket)
    try:
        # Send welcome
        await websocket.send_text(json.dumps({
            "type": "connected",
            "data": {"message": "NEXSYS event stream connected"},
            "timestamp": datetime.utcnow().isoformat(),
        }))

        # Keep alive and listen for pings
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(websocket)


def get_connected_count() -> int:
    return len(_clients)
