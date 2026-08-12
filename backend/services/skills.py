"""Skills engine — loads and executes skill JSON contracts.

Skills are JSON definitions of repeatable actions (publish post, reply to comment, etc.).
This engine reads the contract and executes the steps.
"""
import json
from pathlib import Path
from typing import Any
from ..core.config import DATA_DIR, ensure_data_dir
from ..core.errors import ConflictError
from ..models.schemas import TaskCreate, TaskStatus
from . import tasks as task_svc
from . import graph as graph_svc
from ..core.jsonio import read_json, write_json


def _get_skills_dir() -> Path:
    return DATA_DIR / "skills"


def _ensure_skills_dir():
    ensure_data_dir()
    _get_skills_dir().mkdir(parents=True, exist_ok=True)


def list_skills() -> list[dict]:
    """List all available skill contracts."""
    from . import runtime_settings

    _ensure_skills_dir()
    skills = []
    for f in sorted(_get_skills_dir().glob("*.json")):
        try:
            data = read_json(f, {})
            skills.append({
                "id": f.stem,
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "category": data.get("category", "general"),
                "steps": len(data.get("steps", [])),
                "enabled": runtime_settings.is_skill_enabled(f.stem),
            })
        except Exception:
            pass
    return skills


def set_enabled(skill_id: str, enabled: bool) -> dict:
    """Включает или выключает скилл. Сам контракт остаётся на диске.

    Выключение — не удаление: файл никуда не девается, скилл просто
    перестаёт запускаться, пока его не вернут.
    """
    from . import runtime_settings

    get_skill(skill_id)  # проверяем, что такой есть — иначе NotFound
    runtime_settings.set_skill_enabled(skill_id, enabled)
    return {"id": skill_id, "enabled": enabled}


def get_skill(skill_id: str) -> dict:
    """Load a skill contract by ID."""
    _ensure_skills_dir()
    path = _get_skills_dir() / f"{skill_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Skill '{skill_id}' not found")
    return read_json(path, {})


def execute_skill(skill_id: str, params: dict[str, Any] = None) -> dict:
    """Execute a skill contract with given parameters.

    Each step in the contract defines:
    - action: what to do (create_task, add_graph_node, log, etc.)
    - params: template with {variable} placeholders
    - condition: optional guard (always, if_flag, etc.)

    Returns execution log with step results.
    """
    from . import runtime_settings

    contract = get_skill(skill_id)

    # Выключенный скилл не запускается ни человеком, ни агентом — иначе
    # переключатель был бы украшением, а не запретом.
    if not runtime_settings.is_skill_enabled(skill_id):
        raise ConflictError(f"Скилл '{skill_id}' выключен — включите его перед запуском")

    params = params or {}
    log = []

    for i, step in enumerate(contract.get("steps", [])):
        action = step.get("action", "log")
        step_params = _resolve_params(step.get("params", {}), params)
        condition = step.get("condition", "always")

        # Check condition
        if condition != "always":
            if condition.startswith("if:"):
                flag = condition[3:]
                if not params.get(flag):
                    log.append({"step": i, "action": action, "status": "skipped", "reason": f"condition '{condition}' not met"})
                    continue

        try:
            result = _execute_step(action, step_params)
            log.append({"step": i, "action": action, "status": "ok", "result": result})
        except Exception as e:
            log.append({"step": i, "action": action, "status": "error", "error": str(e)})
            if step.get("required", False):
                break  # stop on required step failure

    # Log execution to graph
    try:
        graph_svc.add_node(graph_svc.GraphNode(
            id=f"skill-run:{skill_id}:{len(log)}",
            label=f"Skill: {contract.get('name', skill_id)}",
            node_type=graph_svc.NodeType.DECISION,
            metadata={"skill_id": skill_id, "steps_executed": len(log), "params": params},
        ))
    except Exception:
        pass

    return {
        "skill_id": skill_id,
        "skill_name": contract.get("name", skill_id),
        "steps_executed": len(log),
        "log": log,
    }


def _resolve_params(template: dict, values: dict) -> dict:
    """Replace {variable} placeholders in template with values."""
    resolved = {}
    for k, v in template.items():
        if isinstance(v, str):
            for key, val in values.items():
                v = v.replace(f"{{{key}}}", str(val))
            resolved[k] = v
        elif isinstance(v, dict):
            resolved[k] = _resolve_params(v, values)
        else:
            resolved[k] = v
    return resolved


def _execute_step(action: str, params: dict) -> Any:
    """Execute a single skill step."""
    if action == "create_task":
        task = task_svc.create_task(TaskCreate(
            title=params.get("title", "Skill task"),
            description=params.get("description", ""),
            assigned_agent=params.get("assigned_agent"),
            tags=params.get("tags", []),
        ))
        return {"task_id": task.id}

    elif action == "add_graph_node":
        node = graph_svc.add_node(graph_svc.GraphNode(
            id=params.get("id", ""),
            label=params.get("label", ""),
            node_type=params.get("node_type", "concept"),
            metadata=params.get("metadata", {}),
        ))
        return {"node_id": node.id}

    elif action == "add_graph_edge":
        edge = graph_svc.add_edge(graph_svc.GraphEdge(
            source=params.get("source", ""),
            target=params.get("target", ""),
            edge_type=params.get("edge_type", "related"),
        ))
        return {"edge": f"{edge.source} -> {edge.target}"}

    elif action == "log":
        return {"message": params.get("message", "step executed")}

    elif action == "set_flag":
        return {"flag": params.get("flag"), "value": params.get("value", True)}

    else:
        raise ValueError(f"Unknown action: {action}")


def create_default_skills():
    """Create default skill contracts for content production."""
    _ensure_skills_dir()

    defaults = {
        "publish-post": {
            "name": "Publish Post",
            "description": "Create and publish a social media post",
            "category": "content",
            "steps": [
                {"action": "create_task", "params": {"title": "Draft post: {topic}", "description": "Create draft for {platform}", "tags": ["content", "draft"]}},
                {"action": "add_graph_node", "params": {"id": "post:{topic}", "label": "Post: {topic}", "node_type": "document"}},
                {"action": "log", "params": {"message": "Post draft created for {topic} on {platform}"}},
            ],
        },
        "reply-comment": {
            "name": "Reply to Comment",
            "description": "Draft a reply to a social media comment",
            "category": "content",
            "steps": [
                {"action": "create_task", "params": {"title": "Reply to comment on {post_id}", "description": "Comment: {comment_text}", "tags": ["content", "reply"]}},
                {"action": "log", "params": {"message": "Reply task created for comment on {post_id}"}},
            ],
        },
        "crisis-escalate": {
            "name": "Crisis Escalation",
            "description": "Escalate a negative situation to human review",
            "category": "safety",
            "steps": [
                {"action": "create_task", "params": {"title": "CRISIS: {issue}", "description": "Escalated from {source}. Requires immediate attention.", "tags": ["crisis", "urgent"], "assigned_agent": "jarvis"}},
                {"action": "add_graph_node", "params": {"id": "crisis:{issue}", "label": "Crisis: {issue}", "node_type": "decision"}},
                {"action": "log", "params": {"message": "Crisis escalated: {issue}"}},
            ],
        },
        "collect-metrics": {
            "name": "Collect Metrics",
            "description": "Gather and record performance metrics",
            "category": "analytics",
            "steps": [
                {"action": "add_graph_node", "params": {"id": "metrics:{date}", "label": "Metrics: {date}", "node_type": "session", "metadata": {"type": "metrics"}}},
                {"action": "log", "params": {"message": "Metrics collected for {date}"}},
            ],
        },
    }

    for skill_id, contract in defaults.items():
        path = _get_skills_dir() / f"{skill_id}.json"
        if not path.exists():
            write_json(path, contract)

    return list(defaults.keys())
