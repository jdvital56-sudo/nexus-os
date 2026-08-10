"""Task API routes."""
from fastapi import APIRouter, Depends
from ..models.schemas import Task, TaskCreate, TaskUpdate
from ..services import tasks as svc
from ..core.auth import get_token_dep

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
auth = get_token_dep()


@router.get("", response_model=list[Task])
def list_t(status: str | None = None, assigned_agent: str | None = None, _=Depends(auth)):
    return svc.list_tasks(status=status, assigned_agent=assigned_agent)


@router.get("/{task_id}", response_model=Task)
def get_t(task_id: str, _=Depends(auth)):
    return svc.get_task(task_id)


@router.post("", response_model=Task, status_code=201)
def create_t(data: TaskCreate, _=Depends(auth)):
    return svc.create_task(data)


@router.patch("/{task_id}", response_model=Task)
def update_t(task_id: str, data: TaskUpdate, _=Depends(auth)):
    return svc.update_task(task_id, data)


@router.delete("/{task_id}")
def delete_t(task_id: str, _=Depends(auth)):
    svc.delete_task(task_id)
    return {"ok": True}
