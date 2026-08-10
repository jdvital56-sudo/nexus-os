"""Skills API routes."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Any
from ..services import skills as svc
from ..core.auth import get_token_dep

router = APIRouter(prefix="/api/skills", tags=["skills"])
auth = get_token_dep()


@router.get("")
def list_skills(_=Depends(auth)):
    return svc.list_skills()


@router.get("/{skill_id}")
def get_skill(skill_id: str, _=Depends(auth)):
    return svc.get_skill(skill_id)


class SkillRunRequest(BaseModel):
    params: dict[str, Any] = {}


@router.post("/{skill_id}/run")
def run_skill(skill_id: str, req: SkillRunRequest, _=Depends(auth)):
    return svc.execute_skill(skill_id, req.params)
