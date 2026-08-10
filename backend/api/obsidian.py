"""Obsidian sync API routes."""
from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel
from ..services import obsidian_sync as svc
from ..core.auth import get_token_dep

router = APIRouter(prefix="/api/obsidian", tags=["obsidian"])
auth = get_token_dep()


@router.get("/status")
def status(_=Depends(auth)):
    return svc.get_sync_status()


class ScanRequest(BaseModel):
    vault_path: str


@router.post("/scan")
def scan(req: ScanRequest, _=Depends(auth)):
    try:
        return svc.scan_vault(req.vault_path)
    except FileNotFoundError as e:
        return {"error": str(e)}


class SyncRequest(BaseModel):
    vault_path: str
    incremental: bool = True


@router.post("/sync")
def sync(req: SyncRequest, _=Depends(auth)):
    try:
        return svc.sync_vault(req.vault_path, incremental=req.incremental)
    except FileNotFoundError as e:
        return {"error": str(e)}


@router.post("/reset")
def reset(_=Depends(auth)):
    svc.clear_sync_state()
    return {"ok": True}
