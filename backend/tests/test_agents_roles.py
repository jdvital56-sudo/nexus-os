"""Test all 6 agent roles execute real cycles."""
import pytest

from backend.core.config import settings
from backend.services.llm import LLMService


@pytest.fixture(autouse=True)
def no_real_external_calls(monkeypatch):
    """23.08.2026: Researcher/Reviewer/Builder теперь реально зовут веб-поиск
    и модель, когда им дают конкретную задачу (ctx.task) — эти тесты
    передают произвольный текст в task, и без этой заглушки они бы
    стучались в настоящие Firecrawl/DeepSeek (деньги, сеть, недетерминизм).
    Реальные пути проверяются отдельно в test_agent_engine_researcher.py /
    _reviewer.py / _builder.py с моками."""
    monkeypatch.setattr(settings, "firecrawl_api_key", "")

    async def fake_generate_response(self, prompt, context="", kind="interactive", json_mode=False):
        return "OK: тестовая заглушка, реальный вызов не делался"

    monkeypatch.setattr(LLMService, "generate_response", fake_generate_response)


def test_builder_cycle(client):
    r = client.post("/api/agents", json={"name": "Build", "role": "builder"})
    aid = r.json()["id"]
    r = client.post(f"/api/agents/{aid}/run", json={"task": "build feature"})
    data = r.json()
    assert data["status"] == "completed"
    assert "builder" in data["output"].lower()


def test_researcher_cycle_sweep_without_a_task(client):
    """Пустая задача — прежний автономный обход графа на слабо связанные
    узлы (плановый прогон, не директива с конкретным вопросом)."""
    r = client.post("/api/agents", json={"name": "Research", "role": "researcher"})
    aid = r.json()["id"]
    # Add some sparse nodes
    client.post("/api/graph/nodes", json={"id": "sparse1", "label": "Sparse", "node_type": "concept"})
    r = client.post(f"/api/agents/{aid}/run", json={"task": ""})
    data = r.json()
    assert data["status"] == "completed"
    assert "research" in data["output"].lower()


def test_researcher_cycle_directed_without_search_key(client):
    """Конкретная задача, но веб-поиск не настроен (фикстура выше) —
    честно говорит об этом в логе, не делает вид, что исследовал, и не
    заводит задачу «кто-то пусть посмотрит» вместо реальной работы."""
    r = client.post("/api/agents", json={"name": "Research", "role": "researcher"})
    aid = r.json()["id"]
    r = client.post(f"/api/agents/{aid}/run", json={"task": "почему голос отвечает с задержкой"})
    data = r.json()
    assert data["status"] == "completed"
    assert "не настроен" in data["output"]


def test_monitor_cycle(client):
    r = client.post("/api/agents", json={"name": "Watch", "role": "monitor"})
    aid = r.json()["id"]
    r = client.post(f"/api/agents/{aid}/run", json={"task": "check health"})
    data = r.json()
    assert data["status"] == "completed"
    assert "monitor" in data["output"].lower()


def test_jarvis_cycle(client):
    # Create some tasks
    client.post("/api/tasks", json={"title": "Urgent review", "priority": "high", "tags": ["review"]})
    client.post("/api/tasks", json={"title": "Build feature", "priority": "critical", "tags": ["build"]})

    r = client.post("/api/agents", json={"name": "Jarvis", "role": "jarvis"})
    aid = r.json()["id"]
    r = client.post(f"/api/agents/{aid}/run", json={"task": "orchestrate"})
    data = r.json()
    assert data["status"] == "completed"
    assert "jarvis" in data["output"].lower() or "orchestrat" in data["output"].lower()


def test_all_roles_exist(client):
    """All 6 roles should have working cycles."""
    roles = ["librarian", "reviewer", "builder", "researcher", "monitor", "jarvis"]
    for role in roles:
        r = client.post("/api/agents", json={"name": f"Test {role}", "role": role})
        assert r.status_code == 201, f"Failed to create {role} agent"
        aid = r.json()["id"]
        r = client.post(f"/api/agents/{aid}/run", json={"task": f"test {role}"})
        assert r.status_code == 200, f"Failed to run {role} agent"
        assert r.json()["status"] == "completed", f"{role} agent did not complete"
