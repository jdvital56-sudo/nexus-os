"""Исследователь — направления поиска и разведка трендов по кнопке.

Находки попадают в «Идеи» (см. services/researcher.py), поэтому своих
ручек на выдачу здесь нет: список читается обычным /api/ideas.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..core.auth import get_token_dep
from ..models.schemas import Idea
from ..services import researcher as svc

router = APIRouter(prefix="/api/researcher", tags=["researcher"])
auth = get_token_dep()


class DirectionsRequest(BaseModel):
    directions: list[str]


@router.get("/directions", response_model=list[str])
def get_directions(_=Depends(auth)):
    return svc.get_directions()


@router.put("/directions", response_model=list[str])
def set_directions(req: DirectionsRequest, _=Depends(auth)):
    return svc.set_directions(req.directions)


@router.post("/run", response_model=list[Idea])
async def run(direction: str | None = None, _=Depends(auth)):
    """Разведка сейчас. Без направления обходит все настроенные."""
    if direction:
        return await svc.research(direction)

    found: list[Idea] = []
    for d in svc.get_directions():
        found.extend(await svc.research(d))
    return found
