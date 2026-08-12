"""Маршруты Куратора — гигиена памяти."""
from fastapi import APIRouter, Depends

from ..core.auth import get_token_dep
from ..services import curator as svc

router = APIRouter(prefix="/api/curator", tags=["curator"])
auth = get_token_dep()


@router.get("/stats")
def stats_c(_=Depends(auth)):
    return svc.get_stats()


@router.get("/inspect")
def inspect_c(_=Depends(auth)):
    """Что Куратор собирается тронуть. Ничего не меняет."""
    return svc.run_cycle(apply=False)


@router.post("/run")
def run_c(apply: bool = False, _=Depends(auth)):
    """Проход уборки. Без apply=true остаётся осмотром."""
    return svc.run_cycle(apply=apply)


@router.get("/archive")
def archive_c(_=Depends(auth)):
    return svc.list_archive()


@router.post("/restore/{fact_id}")
def restore_c(fact_id: str, _=Depends(auth)):
    """Возвращает запись из архива обратно в память."""
    return svc.restore(fact_id)
