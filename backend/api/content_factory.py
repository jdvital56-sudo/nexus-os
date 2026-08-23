"""Content Factory API — идея -> сценарии -> озвучка -> approve/reject.

Ручки нарочно узкие: план генерируется отдельно от озвучки одного черновика
(тяжёлая LLM-генерация N сценариев не должна ждать N синтезов голоса), а
approve/reject не делает ничего, кроме смены статуса — публикации в системе
нет, забирает готовый файл сам человек.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from ..core.auth import get_token_dep
from ..models.schemas import ContentItem, ContentPlanRequest, ContentStatus
from ..services import content_factory as svc

router = APIRouter(prefix="/api/content", tags=["content-factory"])
auth = get_token_dep()


@router.get("", response_model=list[ContentItem])
def list_items(status: str | None = None, _=Depends(auth)):
    return svc.list_items(status=status)


@router.get("/{item_id}", response_model=ContentItem)
def get_item(item_id: str, _=Depends(auth)):
    return svc.get_item(item_id)


@router.post("/plan", response_model=list[ContentItem], status_code=201)
async def create_plan(req: ContentPlanRequest, _=Depends(auth)):
    return await svc.generate_plan(req.topic, req.count, req.platforms)


@router.post("/{item_id}/voice", response_model=ContentItem)
async def synthesize_voice(item_id: str, _=Depends(auth)):
    return await svc.synthesize_voice(item_id)


@router.get("/{item_id}/voice")
def download_voice(item_id: str, _=Depends(auth)):
    path = svc.voice_file_path(item_id)
    return FileResponse(path, filename=path.name)


@router.post("/{item_id}/image", response_model=ContentItem)
async def generate_image(item_id: str, prompt: str | None = None, _=Depends(auth)):
    return await svc.generate_image(item_id, prompt)


@router.get("/{item_id}/image")
def download_image(item_id: str, _=Depends(auth)):
    path = svc.image_file_path(item_id)
    return FileResponse(path, filename=path.name)


@router.post("/{item_id}/video", response_model=ContentItem)
async def generate_video(item_id: str, prompt: str | None = None, _=Depends(auth)):
    return await svc.generate_video(item_id, prompt)


@router.get("/{item_id}/video")
def download_video(item_id: str, _=Depends(auth)):
    path = svc.video_file_path(item_id)
    return FileResponse(path, filename=path.name)


@router.post("/{item_id}/approve", response_model=ContentItem)
def approve(item_id: str, _=Depends(auth)):
    return svc.set_status(item_id, ContentStatus.APPROVED)


@router.post("/{item_id}/reject", response_model=ContentItem)
def reject(item_id: str, _=Depends(auth)):
    return svc.set_status(item_id, ContentStatus.REJECTED)


@router.delete("/{item_id}")
def delete_item(item_id: str, _=Depends(auth)):
    svc.delete_item(item_id)
    return {"ok": True}
