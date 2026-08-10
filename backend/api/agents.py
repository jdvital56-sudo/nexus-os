"""Agent API routes."""
from fastapi import APIRouter, Depends
from ..models.schemas import Agent, AgentCreate, AgentUpdate, AgentRunRequest, AgentRunResult
from ..services import agents as svc
from ..core.auth import get_token_dep

router = APIRouter(prefix="/api/agents", tags=["agents"])
auth = get_token_dep()


@router.get("", response_model=list[Agent])
def list_a(role: str | None = None, _=Depends(auth)):
    return svc.list_agents(role=role)


@router.get("/{agent_id}", response_model=Agent)
def get_a(agent_id: str, _=Depends(auth)):
    return svc.get_agent(agent_id)


@router.post("", response_model=Agent, status_code=201)
def create_a(data: AgentCreate, _=Depends(auth)):
    return svc.create_agent(data)


@router.patch("/{agent_id}", response_model=Agent)
def update_a(agent_id: str, data: AgentUpdate, _=Depends(auth)):
    return svc.update_agent(agent_id, data)


@router.delete("/{agent_id}")
def delete_a(agent_id: str, _=Depends(auth)):
    svc.delete_agent(agent_id)
    return {"ok": True}


@router.post("/{agent_id}/run", response_model=AgentRunResult)
def run_a(agent_id: str, req: AgentRunRequest, _=Depends(auth)):
    return svc.run_agent(agent_id, req.task, req.context)
