"""Content Factory API — идея -> сценарии -> озвучка -> approve/reject.

Ручки нарочно узкие: план генерируется отдельно от озвучки одного черновика
(тяжёлая LLM-генерация N сценариев не должна ждать N синтезов голоса), а
approve/reject не делает ничего, кроме смены статуса — публикации в системе
нет, забирает готовый файл сам человек.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.auth import _load_token, get_token_dep
from ..models.schemas import ContentItem, ContentPlanRequest, ContentStatus
from ..services import content_factory as svc

router = APIRouter(prefix="/api/content", tags=["content-factory"])
auth = get_token_dep()


def _verify_query_token(token: str | None = Query(None)) -> bool:
    """Проверка токена из строки запроса — для тегов <img> и <audio>.

    23.08.2026, найдено живым прогоном: карточка контента показывала
    готовую картинку и озвучку через <img src>/<audio src>, а эти теги
    физически не умеют слать заголовок Authorization — браузер получал
    401, и на экране была пустота вместо реально сгенерированных файлов.
    Тот же приём и та же оговорка, что у /api/voice/say-stream: касается
    ТОЛЬКО отдачи готовых медиафайлов, остальные ручки как были, на
    HTTPBearer.
    """
    stored = _load_token()
    if not stored:
        return True
    if token != stored:
        raise HTTPException(status_code=401, detail="Invalid token")
    return True


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
def download_voice(item_id: str, _=Depends(_verify_query_token)):
    path = svc.voice_file_path(item_id)
    return FileResponse(path, filename=path.name)


@router.post("/{item_id}/image", response_model=ContentItem)
async def generate_image(item_id: str, prompt: str | None = None, _=Depends(auth)):
    return await svc.generate_image(item_id, prompt)


@router.get("/{item_id}/image")
def download_image(item_id: str, _=Depends(_verify_query_token)):
    path = svc.image_file_path(item_id)
    return FileResponse(path, filename=path.name)


@router.post("/{item_id}/video", response_model=ContentItem)
async def generate_video(item_id: str, prompt: str | None = None, _=Depends(auth)):
    return await svc.generate_video(item_id, prompt)


@router.get("/{item_id}/video")
def download_video(item_id: str, _=Depends(_verify_query_token)):
    path = svc.video_file_path(item_id)
    return FileResponse(path, filename=path.name)


class ScheduleRequest(BaseModel):
    scheduled_at: str


class PlatformsRequest(BaseModel):
    platforms: list[str]


@router.post("/{item_id}/schedule", response_model=ContentItem)
def schedule(item_id: str, req: ScheduleRequest, _=Depends(auth)):
    return svc.schedule_item(item_id, req.scheduled_at)


@router.post("/{item_id}/platforms", response_model=ContentItem)
def set_platforms(item_id: str, req: PlatformsRequest, _=Depends(auth)):
    return svc.set_platforms(item_id, req.platforms)


@router.post("/{item_id}/send-approval", response_model=ContentItem)
async def send_approval(item_id: str, _=Depends(auth)):
    """Отправляет черновик кнопками в Telegram. Статус меняется только если
    сообщение реально ушло — см. content_factory.send_for_approval."""
    return await svc.send_for_approval(item_id)


@router.post("/{item_id}/posted", response_model=ContentItem)
def mark_posted(item_id: str, _=Depends(auth)):
    return svc.mark_posted(item_id)


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
