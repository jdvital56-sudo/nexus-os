"""Content pipeline tests."""
import pytest

from backend.services.llm import LLMService


@pytest.fixture(autouse=True)
def no_real_llm_calls(monkeypatch):
    """23.08.2026: Reviewer теперь реально зовёт LLM, когда ему дают
    конкретную задачу (ctx.task) — content_pipeline.advance() запускает
    его fire-and-forget при draft→review (результат отбрасывается, но
    вызов настоящий). Без заглушки эти тесты стучались бы в настоящий
    DeepSeek за реальные деньги."""

    async def fake_generate_response(self, prompt, context="", kind="interactive", json_mode=False):
        return "OK: тестовая заглушка, реальный вызов не делался"

    monkeypatch.setattr(LLMService, "generate_response", fake_generate_response)


def test_create_content(client):
    r = client.post("/api/pipeline/content", json={
        "title": "AI Agents Guide",
        "platform": "instagram",
        "description": "How to build AI agents",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "AI Agents Guide"
    assert data["stage"] == "idea"
    assert data["platform"] == "instagram"


def test_pipeline_status(client):
    r = client.get("/api/pipeline/status")
    assert r.status_code == 200
    data = r.json()
    assert "total_items" in data
    assert "stages" in data


def test_list_content(client):
    client.post("/api/pipeline/content", json={"title": "Post 1"})
    client.post("/api/pipeline/content", json={"title": "Post 2"})
    r = client.get("/api/pipeline/content")
    assert len(r.json()) >= 2


def test_advance_idea_to_draft(client):
    r = client.post("/api/pipeline/content", json={"title": "Test Post", "platform": "twitter"})
    content_id = r.json()["content_id"]

    r = client.post(f"/api/pipeline/content/{content_id}/advance", json={
        "content_text": "This is the draft content for the post about AI.",
    })
    data = r.json()
    assert data["stage"] == "draft"
    assert "document_id" in data.get("metadata", {})


def test_advance_draft_to_review(client, tmp_path):
    # Create reviewer agent
    client.post("/api/agents", json={"name": "QA", "role": "reviewer"})

    r = client.post("/api/pipeline/content", json={"title": "Review Me"})
    content_id = r.json()["content_id"]

    # idea → draft
    client.post(f"/api/pipeline/content/{content_id}/advance", json={"content_text": "Draft text"})

    # draft → review
    r = client.post(f"/api/pipeline/content/{content_id}/advance", json={"content_text": "Draft text"})
    data = r.json()
    assert data["stage"] == "review"


def test_advance_full_pipeline(client):
    """Move content through all stages."""
    r = client.post("/api/pipeline/content", json={"title": "Full Run", "platform": "blog"})
    content_id = r.json()["content_id"]

    # idea → draft
    r = client.post(f"/api/pipeline/content/{content_id}/advance", json={"content_text": "Content here"})
    assert r.json()["stage"] == "draft"

    # draft → review
    r = client.post(f"/api/pipeline/content/{content_id}/advance", json={})
    assert r.json()["stage"] == "review"

    # review → approve (no review task blocking)
    r = client.post(f"/api/pipeline/content/{content_id}/advance", json={})
    assert r.json()["stage"] == "approve"

    # approve → schedule
    r = client.post(f"/api/pipeline/content/{content_id}/advance", json={})
    assert r.json()["stage"] == "schedule"

    # schedule → publish
    r = client.post(f"/api/pipeline/content/{content_id}/advance", json={})
    assert r.json()["stage"] == "publish"

    # publish → metrics
    r = client.post(f"/api/pipeline/content/{content_id}/advance", json={})
    assert r.json()["stage"] == "metrics"


def test_content_not_found(client):
    r = client.post("/api/pipeline/content/nonexistent/advance", json={})
    assert "error" in r.json()
