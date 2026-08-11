"""Gmail API — черновики и чтение. Отправки нет ни здесь, ни в сервисе."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.auth import get_token_dep
from ..services.gmail import GmailNotConfigured, gmail_client

router = APIRouter(prefix="/api/gmail", tags=["gmail"])
auth = get_token_dep()


class DraftCreate(BaseModel):
    to: str
    subject: str
    body: str
    cc: str = ""
    reply_to: str = ""


@router.get("/status")
def status(_=Depends(auth)):
    return {
        "configured": gmail_client.is_configured(),
        "can_send": False,
        "note": "Отправка писем не реализована намеренно: система готовит черновик, "
                "отправляет человек (хартия §6, принцип 3)",
    }


@router.post("/drafts", status_code=201)
def create_draft(req: DraftCreate, _=Depends(auth)):
    try:
        return gmail_client.create_draft(**req.model_dump())
    except GmailNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/drafts")
def list_drafts(limit: int = 10, _=Depends(auth)):
    try:
        return gmail_client.list_drafts(limit=limit)
    except GmailNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/search")
def search(q: str, limit: int = 10, _=Depends(auth)):
    try:
        return gmail_client.search(q, limit=limit)
    except GmailNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
