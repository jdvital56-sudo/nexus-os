"""Artifacts API — единая папка того, что система сгенерировала."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.auth import get_token_dep
from ..services import artifacts as svc

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])
auth = get_token_dep()


class ArtifactCreate(BaseModel):
    title: str
    content: str
    description: str
    kind: str = "document"
    extension: str = "md"
    source: str = ""


class DeleteRequest(BaseModel):
    reason: str = ""


@router.get("")
def list_artifacts(status: str | None = None, kind: str | None = None, _=Depends(auth)):
    return svc.list_artifacts(status=status, kind=kind)


@router.post("", status_code=201)
def create_artifact(req: ArtifactCreate, _=Depends(auth)):
    try:
        return svc.save(**req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/adopt")
def adopt_orphans(_=Depends(auth)):
    """Занести в реестр файлы, появившиеся в папке мимо системы."""
    return {"adopted": svc.adopt_orphans()}


@router.get("/{artifact_id}")
def get_artifact(artifact_id: str, _=Depends(auth)):
    return svc.get_artifact(artifact_id)


@router.get("/{artifact_id}/content")
def read_artifact(artifact_id: str, _=Depends(auth)):
    try:
        return {"content": svc.read_artifact(artifact_id)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{artifact_id}/request-delete")
def request_delete(artifact_id: str, req: DeleteRequest, _=Depends(auth)):
    """Пометить к удалению. Файл остаётся — стирает только человек."""
    return svc.request_delete(artifact_id, reason=req.reason)


@router.post("/{artifact_id}/cancel-delete")
def cancel_delete(artifact_id: str, _=Depends(auth)):
    return svc.cancel_delete(artifact_id)


@router.delete("/{artifact_id}")
def delete_artifact(artifact_id: str, confirmed: bool = False, _=Depends(auth)):
    """Необратимое действие: без ?confirmed=true не выполняется."""
    try:
        return svc.delete(artifact_id, confirmed=confirmed)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
