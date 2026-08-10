"""Content pipeline API routes."""
from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel
from typing import Any
from ..services import content_pipeline as svc
from ..core.auth import get_token_dep

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])
auth = get_token_dep()


class CreateContentRequest(BaseModel):
    title: str
    platform: str = "general"
    description: str = ""


@router.post("/content")
def create_content(req: CreateContentRequest, _=Depends(auth)):
    item = svc.create_content(req.title, req.platform, req.description)
    return item.to_dict()


class AdvanceRequest(BaseModel):
    content_text: str = ""


@router.post("/content/{content_id}/advance")
def advance(content_id: str, req: AdvanceRequest, _=Depends(auth)):
    # Find the content item
    items = svc.list_content()
    item_data = None
    for i in items:
        if i["content_id"] == content_id:
            item_data = i
            break
    if not item_data:
        return {"error": f"Content '{content_id}' not found"}

    # Reconstruct ContentItem
    item = svc.ContentItem(content_id, item_data["title"], item_data["platform"])
    item.stage = item_data["stage"]

    # Advance
    item = svc.advance_stage(item, req.content_text)
    return item.to_dict()


@router.get("/status")
def status(_=Depends(auth)):
    return svc.get_pipeline_status()


@router.get("/content")
def list_content(stage: str | None = None, _=Depends(auth)):
    return svc.list_content(stage)
