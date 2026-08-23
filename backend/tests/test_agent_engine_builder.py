"""Builder: настоящий план реализации при конкретной задаче (23.08.2026).

Раньше act_builder всегда просто помечал существующую задачу статусом
«в работе» и добавлял узел графа — кода не писал и плана не предлагал,
даже по прямой просьбе «напиши код для X». Фаундер прямо сказал: агенты
должны реально работать, не быть трекерами.

Сознательное ограничение: Строитель НЕ пишет файлы в боевом репозитории и
не коммитит сам — только предлагает план, который проверяет человек (то
же правило «безопасность важнее самостоятельности», что у computer_use.py).
"""
from backend.models.schemas import Agent, AgentRole
from backend.services import agent_engine
from backend.services import memory as mem_svc
from backend.services.llm import LLMService


def _agent() -> Agent:
    return Agent(id="test-builder", name="Build", role=AgentRole.BUILDER)


def test_directed_build_proposes_a_plan_and_stores_it(monkeypatch):
    async def fake_generate_response(self, prompt, context="", kind="interactive", json_mode=False):
        assert "добавить кнопку экспорта в CSV" in prompt
        return "1. backend/api/export.py: новый роут GET /api/export/csv.\n2. Фронтенд: кнопка в TasksScreen.tsx."

    monkeypatch.setattr(LLMService, "generate_response", fake_generate_response)

    result = agent_engine.execute_cycle(_agent(), "добавить кнопку экспорта в CSV на экране задач")

    assert result["status"] == "completed"
    assert result["result"]["verify"]["status"] == "proposed"
    assert "export.py" in result["result"]["verify"]["plan"]
    assert "export.py" in result["output"]

    facts = [f for f in mem_svc.get_facts(limit=50) if f.source == "builder"]
    assert len(facts) == 1
    assert result["result"]["verify"]["fact_id"] == facts[0].id


def test_directed_build_does_not_touch_tasks_or_graph_nodes(client, monkeypatch):
    """Реальное ограничение безопасности: директива не должна создавать
    build:* узлы графа или менять статусы задач сама по себе — это было
    поведение прежнего (фейкового) пути, не должно остаться побочным
    эффектом настоящего плана."""
    async def fake_generate_response(self, prompt, context="", kind="interactive", json_mode=False):
        return "План: сделать X."

    monkeypatch.setattr(LLMService, "generate_response", fake_generate_response)

    before_tasks = client.get("/api/tasks").json()
    before_nodes = client.get("/api/graph/nodes").json() if _graph_nodes_endpoint_exists(client) else None

    agent_engine.execute_cycle(_agent(), "сделать X")

    assert client.get("/api/tasks").json() == before_tasks
    if before_nodes is not None:
        assert client.get("/api/graph/nodes").json() == before_nodes


def _graph_nodes_endpoint_exists(client) -> bool:
    return client.get("/api/graph/nodes").status_code == 200


def test_directed_build_llm_failure_is_reported_not_swallowed(monkeypatch):
    async def failing_generate_response(self, prompt, context="", kind="interactive", json_mode=False):
        raise RuntimeError("DeepSeek недоступен")

    monkeypatch.setattr(LLMService, "generate_response", failing_generate_response)

    result = agent_engine.execute_cycle(_agent(), "сделай что-нибудь")

    assert result["status"] == "completed"
    assert "DeepSeek недоступен" in result["output"]
    assert [f for f in mem_svc.get_facts(limit=50) if f.source == "builder"] == []


def test_empty_task_still_marks_existing_tasks_in_progress(client, monkeypatch):
    """Пустая задача — не директива, прежнее поведение (взять задачи из
    очереди, пометить «в работе») не сломано этой правкой."""
    client.post("/api/tasks", json={"title": "build something useful"})

    result = agent_engine.execute_cycle(_agent(), "")

    assert result["status"] == "completed"
    assert "builds_started" in result["result"]["verify"]
    assert result["result"]["verify"]["builds_started"] == 1
