"""Потоковый путь tools.py — финальный ответ по кусочкам, раунды с
инструментами всё равно собираются целиком (частичный вызов не исполнить)."""
import json

import httpx
import pytest

from backend.services import tools as tools_svc
from backend.services.llm import LLMMessage, LLMService


def _sse(*objs: dict) -> list[str]:
    lines = [f"data: {json.dumps(o)}" for o in objs]
    lines.append("data: [DONE]")
    return lines


class _FakeStreamResponse:
    def __init__(self, lines: list[str]):
        self._lines = lines

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamCtx:
    def __init__(self, lines: list[str]):
        self._lines = lines

    async def __aenter__(self):
        return _FakeStreamResponse(self._lines)

    async def __aexit__(self, *exc):
        return False


def _fake_llm() -> LLMService:
    llm = LLMService(provider="deepseek", model="deepseek-chat", api_key="test-key")
    return llm


@pytest.mark.asyncio
async def test_plain_stream_yields_content_deltas(monkeypatch):
    rounds = _sse(
        {"choices": [{"delta": {"content": "Привет"}}]},
        {"choices": [{"delta": {"content": ", сэр"}}]},
        {"choices": [{"delta": {}}], "usage": {"total_tokens": 5}},
    )
    monkeypatch.setattr(httpx.AsyncClient, "stream", lambda self, method, url, **kw: _FakeStreamCtx(rounds))

    llm = _fake_llm()
    parts = [d async for d in tools_svc._plain_stream(llm, [LLMMessage(role="user", content="хай")], 0.7, 100, "interactive")]

    assert "".join(parts) == "Привет, сэр"


@pytest.mark.asyncio
async def test_chat_with_tools_stream_without_tools_falls_back_to_plain(monkeypatch):
    rounds = _sse({"choices": [{"delta": {"content": "Ок"}}]})
    monkeypatch.setattr(httpx.AsyncClient, "stream", lambda self, method, url, **kw: _FakeStreamCtx(rounds))

    llm = _fake_llm()
    parts = [
        d
        async for d in tools_svc.chat_with_tools_stream(llm, [LLMMessage(role="user", content="хай")], tools=[])
    ]
    assert "".join(parts) == "Ок"


@pytest.mark.asyncio
async def test_chat_with_tools_stream_direct_answer_no_tool_call(monkeypatch):
    """Модель отвечает сразу, инструмент вообще не понадобился."""
    rounds = _sse(
        {"choices": [{"delta": {"content": "Дважды два "}}]},
        {"choices": [{"delta": {"content": "четыре."}}]},
    )
    monkeypatch.setattr(httpx.AsyncClient, "stream", lambda self, method, url, **kw: _FakeStreamCtx(rounds))

    llm = _fake_llm()
    parts = [
        d
        async for d in tools_svc.chat_with_tools_stream(
            llm, [LLMMessage(role="user", content="сколько будет 2*2")], tools=[tools_svc.SYSTEM_STATUS_SPEC]
        )
    ]
    assert "".join(parts) == "Дважды два четыре."


@pytest.mark.asyncio
async def test_chat_with_tools_stream_executes_tool_then_streams_final(monkeypatch):
    """Раунд 1 — модель просит system_status (без текста), раунд 2 — уже
    финальный ответ по кускам, построенный на результате инструмента."""
    call_log = []

    round_1 = _sse(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "function": {"name": "system_status", "arguments": ""},
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{}"}}]}}
            ]
        },
    )
    round_2 = _sse(
        {"choices": [{"delta": {"content": "Голос "}}]},
        {"choices": [{"delta": {"content": "включён."}}]},
    )
    responses = [round_1, round_2]

    def fake_stream(self, method, url, **kw):
        return _FakeStreamCtx(responses.pop(0))

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    async def fake_execute(name, raw_arguments, action_key=""):
        call_log.append((name, raw_arguments))
        return "TTS-движок: edge (готов)"

    monkeypatch.setattr(tools_svc, "_execute", fake_execute)

    llm = _fake_llm()
    parts = [
        d
        async for d in tools_svc.chat_with_tools_stream(
            llm,
            [LLMMessage(role="user", content="какой у тебя голос")],
            tools=[tools_svc.SYSTEM_STATUS_SPEC],
        )
    ]

    assert "".join(parts) == "Голос включён."
    assert call_log == [("system_status", "{}")]


@pytest.mark.asyncio
async def test_chat_with_tools_stream_gives_up_after_max_rounds(monkeypatch):
    """Модель просит инструмент на каждом круге — не зависаем навечно."""
    tool_round = _sse(
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": 0, "id": "c", "function": {"name": "system_status", "arguments": "{}"}}]}}
            ]
        }
    )
    rounds = [tool_round[:] for _ in range(tools_svc.MAX_ROUNDS + 1)]

    def fake_stream(self, method, url, **kw):
        return _FakeStreamCtx(rounds.pop(0))

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    async def fake_execute(name, raw_arguments, action_key=""):
        return "ok"

    monkeypatch.setattr(tools_svc, "_execute", fake_execute)

    llm = _fake_llm()
    parts = [
        d
        async for d in tools_svc.chat_with_tools_stream(
            llm, [LLMMessage(role="user", content="?")], tools=[tools_svc.SYSTEM_STATUS_SPEC]
        )
    ]
    assert "слишком много обращений" in "".join(parts)
