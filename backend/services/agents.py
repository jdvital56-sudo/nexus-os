"""Agent service — CRUD + run stub."""
import json
import uuid
from datetime import datetime
from ..core.config import AGENTS_FILE, ensure_data_dir
from ..core.errors import NotFoundError
from ..models.schemas import Agent, AgentCreate, AgentUpdate, AgentRole, AgentStatus, AgentRunResult
from ..core.jsonio import read_json, write_json


def _load() -> list[dict]:
    ensure_data_dir()
    if AGENTS_FILE.exists():
        return read_json(AGENTS_FILE, [])
    return []


def _save(agents: list[dict]):
    ensure_data_dir()
    write_json(AGENTS_FILE, agents)


def list_agents(role: str | None = None) -> list[Agent]:
    agents = [Agent(**a) for a in _load()]
    if role:
        agents = [a for a in agents if a.role.value == role]
    return agents


def get_agent(agent_id: str) -> Agent:
    agents = _load()
    for a in agents:
        if a["id"] == agent_id:
            return Agent(**a)
    raise NotFoundError("Agent", agent_id)


def create_agent(data: AgentCreate) -> Agent:
    agents = _load()
    agent = Agent(
        id=str(uuid.uuid4())[:8],
        name=data.name,
        role=data.role,
        description=data.description,
        model=data.model,
        config=data.config,
    )
    agents.append(agent.model_dump())
    _save(agents)
    return agent


def update_agent(agent_id: str, data: AgentUpdate) -> Agent:
    agents = _load()
    for i, a in enumerate(agents):
        if a["id"] == agent_id:
            if data.name is not None:
                a["name"] = data.name
            if data.description is not None:
                a["description"] = data.description
            if data.model is not None:
                a["model"] = data.model
            if data.config is not None:
                a["config"] = data.config
            if data.status is not None:
                a["status"] = data.status.value
            a["updated_at"] = datetime.utcnow().isoformat()
            agents[i] = a
            _save(agents)
            return Agent(**a)
    raise NotFoundError("Agent", agent_id)


def delete_agent(agent_id: str) -> bool:
    agents = _load()
    new_agents = [a for a in agents if a["id"] != agent_id]
    if len(new_agents) == len(agents):
        raise NotFoundError("Agent", agent_id)
    _save(new_agents)
    return True


def run_agent(agent_id: str, task: str, context: dict | None = None) -> AgentRunResult:
    """Execute agent cycle (Orient-Observe-Think-Act-Verify)."""
    from .agent_engine import execute_cycle
    
    agent = get_agent(agent_id)
    # Update status to running
    agents = _load()
    for i, a in enumerate(agents):
        if a["id"] == agent_id:
            a["status"] = "running"
            a["last_run"] = datetime.utcnow().isoformat()
            agents[i] = a
            _save(agents)
            break

    # Execute real cycle
    result = execute_cycle(agent, task, context)

    # Update status back to idle
    agents = _load()
    for i, a in enumerate(agents):
        if a["id"] == agent_id:
            a["status"] = "idle"
            agents[i] = a
            _save(agents)
            break

    return AgentRunResult(
        agent_id=agent_id,
        status=result["status"],
        output=result["output"],
        duration_ms=result["duration_ms"],
        tokens_used=None,
    )
