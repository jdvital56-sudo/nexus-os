"""Voice API — озвучка ответов (PR-24, первый шаг).

Речь наружу отдаётся файлом: браузер играет его сам, без потоков и
websocket'ов. Этого достаточно, чтобы услышать Джарвиса, и не тянет за
собой инфраструктуру, которую потом дорого чинить.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.auth import get_token_dep
from ..services import tts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])
auth = get_token_dep()


class SayRequest(BaseModel):
    text: str
    voice: str | None = None


@router.get("/status")
def status(_=Depends(auth)):
    """Какой движок включён, готов ли он и какие голоса доступны."""
    return tts.status()


@router.post("/say")
async def say(req: SayRequest, _=Depends(auth)):
    try:
        path = await tts.synthesize(req.text, req.voice)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except tts.VoiceUnavailable as e:
        # 503, а не 500: это не поломка, а «не настроено»
        raise HTTPException(status_code=503, detail=str(e))

    return FileResponse(path, media_type="audio/mpeg", filename="voice.mp3")
