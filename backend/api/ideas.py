"""Ideas API routes — раздел «Идеи», отдельно от задач (services/ideas.py)."""
from fastapi import APIRouter, Depends
from ..models.schemas import Idea, IdeaCreate, IdeaUpdate
from ..services import ideas as svc
from ..core.auth import get_token_dep

router = APIRouter(prefix="/api/ideas", tags=["ideas"])
auth = get_token_dep()


@router.get("", response_model=list[Idea])
def list_i(status: str | None = None, _=Depends(auth)):
    return svc.list_ideas(status=status)


@router.get("/{idea_id}", response_model=Idea)
def get_i(idea_id: str, _=Depends(auth)):
    return svc.get_idea(idea_id)


@router.post("", response_model=Idea, status_code=201)
def create_i(data: IdeaCreate, _=Depends(auth)):
    return svc.create_idea(data)


@router.patch("/{idea_id}", response_model=Idea)
def update_i(idea_id: str, data: IdeaUpdate, _=Depends(auth)):
    return svc.update_idea(idea_id, data)


@router.delete("/{idea_id}")
def delete_i(idea_id: str, _=Depends(auth)):
    svc.delete_idea(idea_id)
    return {"ok": True}
