"""Reviewer: настоящий вердикт при конкретной задаче (23.08.2026).

Раньше act_reviewer всегда просто заводил задачу «свяжи узел графа» для
librarian и полностью игнорировал переданную задачу — даже прямая просьба
«проверь этот код» не приводила ни к какому реальному ревью. Фаундер прямо
сказал: агенты должны реально работать, не быть трекерами. Здесь — с
моками, без сети.
"""
import pytest

from backend.models.schemas import Agent, AgentRole
from backend.services import agent_engine
from backend.services import memory as mem_svc
from backend.services.llm import LLMService


def _agent() -> Agent:
    return Agent(id="test-reviewer", name="QA", role=AgentRole.REVIEWER)


def test_directed_review_gives_a_real_verdict_and_stores_it(monkeypatch):
    async def fake_generate_response(self, prompt, context="", kind="interactive", json_mode=False):
        assert "проверь текст черновика" in prompt
        return "Issue: во втором абзаце цена названа дважды с разными числами."

    monkeypatch.setattr(LLMService, "generate_response", fake_generate_response)

    result = agent_engine.execute_cycle(_agent(), "проверь текст черновика на противоречия")

    assert result["status"] == "completed"
    assert result["result"]["verify"]["status"] == "reviewed"
    assert "цена названа дважды" in result["result"]["verify"]["verdict"]
    assert "Issue: во втором абзаце" in result["output"]  # qa_guard.py парсит именно лог

    facts = [f for f in mem_svc.get_facts(limit=50) if f.source == "reviewer"]
    assert len(facts) == 1
    assert result["result"]["verify"]["fact_id"] == facts[0].id


def test_directed_review_says_ok_when_nothing_is_wrong(monkeypatch):
    async def fake_generate_response(self, prompt, context="", kind="interactive", json_mode=False):
        return "OK: черновик выглядит нормально, противоречий не нашёл."

    monkeypatch.setattr(LLMService, "generate_response", fake_generate_response)

    result = agent_engine.execute_cycle(_agent(), "проверь текст черновика")

    assert result["result"]["verify"]["status"] == "reviewed"
    assert "OK:" in result["output"]


def test_directed_review_attaches_git_diff_when_task_mentions_code(monkeypatch):
    captured_prompt = {}

    async def fake_generate_response(self, prompt, context="", kind="interactive", json_mode=False):
        captured_prompt["value"] = prompt
        return "OK: diff выглядит нормально."

    def fake_git_diff(ctx):
        return "diff --git a/foo.py b/foo.py\n+print('hi')"

    monkeypatch.setattr(LLMService, "generate_response", fake_generate_response)
    monkeypatch.setattr(agent_engine, "_git_diff", fake_git_diff)

    agent_engine.execute_cycle(_agent(), "проверь код, который я сейчас изменил")

    assert "diff --git" in captured_prompt["value"]


def test_directed_review_skips_git_diff_when_task_is_not_about_code(monkeypatch):
    """qa_guard.py кладёт в задачу содержимое артефакта целиком — просьба
    рецензировать текст не должна тащить нерелевантный git diff."""
    called = {"git_diff": False}

    async def fake_generate_response(self, prompt, context="", kind="interactive", json_mode=False):
        return "OK: нормально."

    def fake_git_diff(ctx):
        called["git_diff"] = True
        return "diff --git a/foo.py b/foo.py\n+print('hi')"

    monkeypatch.setattr(LLMService, "generate_response", fake_generate_response)
    monkeypatch.setattr(agent_engine, "_git_diff", fake_git_diff)

    agent_engine.execute_cycle(
        _agent(), "Review document 'onboarding'.\nContent:\nПривет, это гайд для новых клиентов."
    )

    assert called["git_diff"] is False


def test_directed_review_llm_failure_is_reported_not_swallowed(monkeypatch):
    async def failing_generate_response(self, prompt, context="", kind="interactive", json_mode=False):
        raise RuntimeError("DeepSeek недоступен")

    monkeypatch.setattr(LLMService, "generate_response", failing_generate_response)

    result = agent_engine.execute_cycle(_agent(), "проверь текст")

    assert result["status"] == "completed"  # цикл не падает целиком
    assert "DeepSeek недоступен" in result["output"]
    assert [f for f in mem_svc.get_facts(limit=50) if f.source == "reviewer"] == []


def test_empty_task_still_does_the_old_orphan_sweep(client):
    """Пустая задача — не директива, прежнее поведение (обход графа на
    узлы без связей) не сломано этой правкой."""
    client.post("/api/graph/nodes", json={"id": "orphan1", "label": "Lonely", "node_type": "document"})

    result = agent_engine.execute_cycle(_agent(), "")

    assert result["status"] == "completed"
    assert "noted" in result["result"]["verify"]
