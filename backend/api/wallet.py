"""Wallet API — реестр платных сервисов и подписок."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.auth import get_token_dep
from ..services import wallet as svc

router = APIRouter(prefix="/api/wallet", tags=["wallet"])
auth = get_token_dep()


class ServiceCreate(BaseModel):
    name: str
    category: str = "other"
    cost: float = 0.0
    currency: str = "USD"
    period: str = svc.PERIOD_MONTHLY
    next_charge: str | None = None
    cancel_url: str = ""
    url: str = ""
    balance_provider: str = ""
    notes: str = ""


class ServiceUpdate(BaseModel):
    category: str | None = None
    cost: float | None = None
    currency: str | None = None
    period: str | None = None
    next_charge: str | None = None
    cancel_url: str | None = None
    url: str | None = None
    balance_provider: str | None = None
    notes: str | None = None
    status: str | None = None


@router.get("/summary")
def summary(_=Depends(auth)):
    """Сводка: сколько уходит в месяц, что скоро спишется, где кончается баланс."""
    return svc.summary()


@router.post("/refresh")
async def refresh(_=Depends(auth)):
    """Обновить балансы там, где провайдер отдаёт их по API."""
    return {"updated": await svc.refresh_balances()}


@router.get("")
def list_services(status: str | None = "active", _=Depends(auth)):
    return svc.list_services(status=status)


@router.post("", status_code=201)
def create_service(req: ServiceCreate, _=Depends(auth)):
    try:
        return svc.add_service(**req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{service_id}")
def get_service(service_id: str, _=Depends(auth)):
    return svc.get_service(service_id)


@router.put("/{service_id}")
def update_service(service_id: str, req: ServiceUpdate, _=Depends(auth)):
    return svc.update_service(service_id, **req.model_dump(exclude_unset=True))


@router.post("/{service_id}/cancelled")
def mark_cancelled(service_id: str, _=Depends(auth)):
    """Отметить, что подписка отменена человеком. Система сама не отменяет."""
    return svc.mark_cancelled(service_id)


@router.delete("/{service_id}")
def remove_service(service_id: str, _=Depends(auth)):
    svc.remove_service(service_id)
    return {"ok": True}
