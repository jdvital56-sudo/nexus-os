"""Dream Cadence API — находки ночного анализа и утренний бриф.

Бэкенд для экрана Dream Review (PR-21): карточки находок с Apply/Skip.
"""
from fastapi import APIRouter, Depends, HTTPException

from ..core.auth import get_token_dep
from ..services import dream as svc

router = APIRouter(prefix="/api/dream", tags=["dream"])
auth = get_token_dep()


@router.get("/findings")
def list_findings(status: str | None = None, run_id: str | None = None, limit: int = 100, _=Depends(auth)):
    return svc.list_findings(status=status, run_id=run_id, limit=limit)


@router.get("/findings/{finding_id}")
def get_finding(finding_id: str, _=Depends(auth)):
    return svc.get_finding(finding_id)


@router.post("/findings/{finding_id}/apply")
def apply_finding(finding_id: str, _=Depends(auth)):
    """Применить находку. Необратимые изменения памяти — только отсюда (I-2)."""
    try:
        return svc.apply(finding_id)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Некорректное действие находки: {e}")


@router.post("/findings/{finding_id}/skip")
def skip_finding(finding_id: str, _=Depends(auth)):
    return svc.skip(finding_id)


@router.get("/brief")
def get_brief(_=Depends(auth)):
    """Утренний бриф из кэша последнего прогона — без синхронного анализа (R-10)."""
    brief = svc.get_brief()
    if not brief:
        raise HTTPException(status_code=404, detail="Ночной прогон ещё не выполнялся")
    return brief
