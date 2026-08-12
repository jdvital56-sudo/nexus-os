"""Маршруты библиотеки источников."""
from fastapi import APIRouter, Depends

from ..core.auth import get_token_dep
from ..models.schemas import Source, SourceCreate, SourceUpdate
from ..services import sources as svc

router = APIRouter(prefix="/api/sources", tags=["sources"])
auth = get_token_dep()


@router.get("", response_model=list[Source])
def list_s(
    topic: str | None = None,
    kind: str | None = None,
    enabled_only: bool = False,
    _=Depends(auth),
):
    return svc.list_sources(topic=topic, kind=kind, enabled_only=enabled_only)


@router.get("/stats")
def stats_s(_=Depends(auth)):
    return svc.get_stats()


@router.get("/due", response_model=list[Source])
def due_s(_=Depends(auth)):
    """Очередь обхода — источники, у которых вышел срок проверки."""
    return svc.due_sources()


@router.get("/{source_id}", response_model=Source)
def get_s(source_id: str, _=Depends(auth)):
    return svc.get_source(source_id)


@router.post("", response_model=Source, status_code=201)
def add_s(data: SourceCreate, _=Depends(auth)):
    return svc.add_source(data)


@router.patch("/{source_id}", response_model=Source)
def update_s(source_id: str, data: SourceUpdate, _=Depends(auth)):
    return svc.update_source(source_id, data)


@router.post("/{source_id}/checked", response_model=Source)
def record_s(source_id: str, ok: bool = True, items_found: int = 0, error: str = "", _=Depends(auth)):
    return svc.record_check(source_id, ok=ok, items_found=items_found, error=error)


@router.delete("/{source_id}")
def delete_s(source_id: str, _=Depends(auth)):
    svc.delete_source(source_id)
    return {"ok": True}
