"""Skills engine tests."""
import json


def test_list_skills_empty(client):
    r = client.get("/api/skills")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_and_run_skill(client, tmp_path):
    """Create a skill contract and execute it."""
    import backend.core.config as cfg

    # Write skill to the patched DATA_DIR
    skills_dir = cfg.DATA_DIR / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    skill = {
        "name": "Test Skill",
        "description": "A test skill",
        "category": "test",
        "steps": [
            {"action": "log", "params": {"message": "Step 1: hello"}},
            {"action": "create_task", "params": {"title": "Skill task: {topic}", "tags": ["skill"]}},
            {"action": "log", "params": {"message": "Step 3: done with {topic}"}},
        ],
    }
    (skills_dir / "test-skill.json").write_text(json.dumps(skill))

    # List
    r = client.get("/api/skills")
    skills = r.json()
    assert any(s["id"] == "test-skill" for s in skills)

    # Get
    r = client.get("/api/skills/test-skill")
    assert r.json()["name"] == "Test Skill"

    # Run
    r = client.post("/api/skills/test-skill/run", json={"params": {"topic": "AI agents"}})
    assert r.status_code == 200
    data = r.json()
    assert data["skill_id"] == "test-skill"
    assert data["steps_executed"] == 3
    assert data["log"][0]["status"] == "ok"
    assert data["log"][1]["status"] == "ok"
    assert data["log"][1]["result"]["task_id"]


def test_run_skill_with_condition(client, tmp_path):
    """Skill step with condition that's not met should be skipped."""
    import backend.core.config as cfg

    skills_dir = cfg.DATA_DIR / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    skill = {
        "name": "Conditional Skill",
        "description": "Test conditions",
        "category": "test",
        "steps": [
            {"action": "log", "params": {"message": "always runs"}},
            {"action": "log", "params": {"message": "only if flag"}, "condition": "if:enable_extra"},
        ],
    }
    (skills_dir / "cond-skill.json").write_text(json.dumps(skill))

    # Run without flag — step 1 skipped
    r = client.post("/api/skills/cond-skill/run", json={"params": {}})
    data = r.json()
    assert data["log"][0]["status"] == "ok"
    assert data["log"][1]["status"] == "skipped"

    # Run with flag — both run
    r = client.post("/api/skills/cond-skill/run", json={"params": {"enable_extra": True}})
    data = r.json()
    assert data["log"][1]["status"] == "ok"


def test_default_skills_created(client):
    """Default skills should be created on startup."""
    from backend.services.skills import create_default_skills
    create_default_skills()  # ensure they exist in patched dir
    r = client.get("/api/skills")
    skills = r.json()
    skill_ids = {s["id"] for s in skills}
    expected = {"publish-post", "reply-comment", "crisis-escalate", "collect-metrics"}
    assert expected.issubset(skill_ids), f"Missing skills: {expected - skill_ids}"
