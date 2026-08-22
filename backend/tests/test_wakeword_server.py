"""Локальный сервер слова-будильника (wakeword/server.py) — до этой сессии
не было ни одного теста. Реальный захват микрофона и загрузку модели Vosk
не тестируем (нужно железо), но логика вокруг них — обычный код, который
может сломаться так же, как любой другой.

testpaths в pyproject.toml — только backend/tests, поэтому тесты живут
здесь, а не рядом с сервером; wakeword/ импортируется как обычный пакет
(namespace-пакет Python 3, __init__.py не нужен), корень репозитория уже
на sys.path благодаря тому, что backend/ сам пакет.
"""
import asyncio
import json

import pytest

from wakeword import server


def _drain_queue() -> None:
    while not server._audio_queue.empty():
        server._audio_queue.get_nowait()


@pytest.fixture(autouse=True)
def clean_module_state():
    """Модульные набор клиентов и очередь звука — не должны течь между
    тестами, оба живут на уровне модуля (реальный сервер — один процесс)."""
    server._clients.clear()
    _drain_queue()
    yield
    server._clients.clear()
    _drain_queue()


class FakeWebSocket:
    def __init__(self, fail: bool = False):
        self.sent: list[str] = []
        self.fail = fail

    async def send(self, message: str) -> None:
        if self.fail:
            import websockets

            raise websockets.ConnectionClosed(None, None)
        self.sent.append(message)


# --- _short_path (найдено 19.08.2026: Vosk не читает пути с кириллицей) ---


def test_short_path_returns_ascii_for_real_directory(tmp_path):
    result = server._short_path(tmp_path)

    assert result
    # Короткий путь всегда чистый ASCII — в этом весь смысл обхода
    assert all(ord(c) < 128 for c in result)


def test_short_path_falls_back_to_original_when_windows_api_fails(monkeypatch, tmp_path):
    """GetShortPathNameW не всегда доступен (не-Windows, ошибка API) —
    не должно падать, должно вернуть исходный путь."""
    class FakeKernel32:
        @staticmethod
        def GetShortPathNameW(path, buf, size):
            return 0  # 0 = ошибка по контракту WinAPI, buf остаётся пустым

    class FakeWindll:
        kernel32 = FakeKernel32()

    monkeypatch.setattr(server.ctypes, "windll", FakeWindll())

    result = server._short_path(tmp_path)

    assert result == str(tmp_path)


# --- _broadcast ---


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_clients():
    a, b = FakeWebSocket(), FakeWebSocket()
    server._clients.update({a, b})

    await server._broadcast({"type": "final", "text": "привет"})

    expected = json.dumps({"type": "final", "text": "привет"}, ensure_ascii=False)
    assert a.sent == [expected]
    assert b.sent == [expected]


@pytest.mark.asyncio
async def test_broadcast_with_no_clients_is_noop():
    await server._broadcast({"type": "final", "text": "тест"})  # не должно бросить


@pytest.mark.asyncio
async def test_broadcast_drops_dead_clients_without_breaking_others():
    """Один клиент отвалился (ConnectionClosed) — остальные всё равно
    должны получить сообщение, а мёртвый убирается из набора."""
    alive, dead = FakeWebSocket(), FakeWebSocket(fail=True)
    server._clients.update({alive, dead})

    await server._broadcast({"type": "final", "text": "привет"})

    assert dead not in server._clients
    assert alive in server._clients
    assert len(alive.sent) == 1


# --- _recognize_loop: правильно ли различает final/partial и "audio"-тип
# от WordBoundary — сама Vosk-модель здесь замокана целиком ---


class FakeRecognizer:
    def __init__(self, results: list[tuple[bool, dict]]):
        # (accept_waveform_result, json_payload) по одному на вызов
        self._results = iter(results)

    def AcceptWaveform(self, data: bytes) -> bool:
        self._current_is_final, self._current_payload = next(self._results)
        return self._current_is_final

    def Result(self) -> str:
        return json.dumps(self._current_payload)

    def PartialResult(self) -> str:
        return json.dumps(self._current_payload)


@pytest.mark.asyncio
async def test_recognize_loop_broadcasts_final_text(monkeypatch):
    monkeypatch.setattr(server, "KaldiRecognizer", lambda model, rate: FakeRecognizer(
        [(True, {"text": "джарвис привет"})]
    ))
    server._audio_queue.put(b"\x00\x00")

    received = []

    async def fake_broadcast(msg):
        received.append(msg)
        raise asyncio.CancelledError  # останавливаем бесконечный цикл после первого куска

    monkeypatch.setattr(server, "_broadcast", fake_broadcast)

    with pytest.raises(asyncio.CancelledError):
        await server._recognize_loop(model=object())

    assert received == [{"type": "final", "text": "джарвис привет"}]


@pytest.mark.asyncio
async def test_recognize_loop_broadcasts_partial_text(monkeypatch):
    monkeypatch.setattr(server, "KaldiRecognizer", lambda model, rate: FakeRecognizer(
        [(False, {"partial": "джар"})]
    ))
    server._audio_queue.put(b"\x00\x00")

    received = []

    async def fake_broadcast(msg):
        received.append(msg)
        raise asyncio.CancelledError

    monkeypatch.setattr(server, "_broadcast", fake_broadcast)

    with pytest.raises(asyncio.CancelledError):
        await server._recognize_loop(model=object())

    assert received == [{"type": "partial", "text": "джар"}]


@pytest.mark.asyncio
async def test_recognize_loop_skips_empty_text(monkeypatch):
    """Тишина/шум — Vosk отдаёт пустую строку, рассылать нечего."""
    monkeypatch.setattr(server, "KaldiRecognizer", lambda model, rate: FakeRecognizer(
        [(True, {"text": ""}), (True, {"text": "теперь есть текст"})]
    ))
    server._audio_queue.put(b"\x00\x00")
    server._audio_queue.put(b"\x00\x00")

    received = []

    async def fake_broadcast(msg):
        received.append(msg)
        if len(received) >= 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(server, "_broadcast", fake_broadcast)

    with pytest.raises(asyncio.CancelledError):
        await server._recognize_loop(model=object())

    assert received == [{"type": "final", "text": "теперь есть текст"}]
