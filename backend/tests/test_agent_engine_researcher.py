"""Researcher: настоящее исследование при конкретной задаче (23.08.2026).

Раньше act_researcher всегда просто заводил ещё одну задачу «кто-то пусть
исследует» — не искал в вебе, не звал модель. Фаундер прямо сказал: агенты
должны реально работать, не быть трекерами. Здесь — с моками, без сети.
"""
import pytest

from backend.core.config import settings
from backend.models.schemas import Agent, AgentRole
from backend.services import agent_engine
from backend.services import memory as mem_svc
from backend.services import websearch
from backend.services.llm import LLMService


@pytest.fixture
def with_search_key(monkeypatch):
    monkeypatch.setattr(settings, "firecrawl_api_key", "fc-test-key")


def _agent() -> Agent:
    return Agent(id="test-researcher", name="Research", role=AgentRole.RESEARCHER)


def test_directed_research_calls_web_search_and_stores_finding(client, with_search_key, monkeypatch):
    async def fake_run_tool(arguments, action_key=""):
        assert arguments["query"] == "почему голос отвечает с задержкой"
        return "[Источник 1] Полный ответ ждёт всего текста модели, потом уже озвучка."

    async def fake_generate_response(self, prompt, context="", kind="interactive", json_mode=False):
        assert "почему голос отвечает с задержкой" in prompt
        return "Задержка — конвейер ждёт весь текст ответа, прежде чем начать озвучку."

    monkeypatch.setattr(websearch, "run_tool", fake_run_tool)
    monkeypatch.setattr(LLMService, "generate_response", fake_generate_response)

    result = agent_engine.execute_cycle(_agent(), "почему голос отвечает с задержкой")

    assert result["status"] == "completed"
    assert result["result"]["verify"]["status"] == "found"
    assert "конвейер ждёт" in result["result"]["verify"]["finding"]

    facts = [f for f in mem_svc.get_facts(limit=50) if f.source == "researcher"]
    assert len(facts) == 1
    assert "конвейер ждёт" in facts[0].content
    assert result["result"]["verify"]["fact_id"] == facts[0].id


def test_directed_research_search_failure_is_reported_not_swallowed(client, with_search_key, monkeypatch):
    async def failing_run_tool(arguments, action_key=""):
        raise RuntimeError("Firecrawl недоступен")

    monkeypatch.setattr(websearch, "run_tool", failing_run_tool)

    result = agent_engine.execute_cycle(_agent(), "что-то важное")

    assert result["status"] == "completed"  # цикл не падает целиком
    assert result["result"]["verify"] == {"research_tasks": 0}
    assert "Firecrawl недоступен" in result["output"]
    # execute_cycle сам кладёт в память сводку любого прогона (_remember_run,
    # source="agent:{id}") — это не то же самое, что настоящая находка
    # исследования (source="researcher"), которой здесь быть не должно.
    assert [f for f in mem_svc.get_facts(limit=50) if f.source == "researcher"] == []


def test_empty_task_still_does_the_old_sweep(client):
    """Пустая задача — не директива, прежнее поведение (обход графа) не
    сломано этой правкой."""
    client.post("/api/graph/nodes", json={"id": "sparse1", "label": "Sparse", "node_type": "concept"})

    result = agent_engine.execute_cycle(_agent(), "")

    assert result["status"] == "completed"
    assert "research_tasks" in result["result"]["verify"]
