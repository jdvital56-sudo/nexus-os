"""Chat API — веб-чат как второй вход в тот же контур мышления (PR-23).

Мозг у системы один: `ConversationService`. Телеграм — тонкий адаптер к
нему, и веб-чат сделан таким же адаптером, а не вторым мозгом (инвариант
I-1). Поэтому память, персоны, характер, скиллы и заметки работают здесь
ровно так же, как в Телеграме, и нить разговора у каналов раздельная.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.auth import get_token_dep
from ..services import chat_log, dialog_history
from ..services.textclean import strip_markdown
from ..services.conversation import get_conversation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])
auth = get_token_dep()

CHANNEL = "web"

# У веб-чата один собеседник — хозяин системы. Отдельные пользователи
# появятся вместе с приложением для заказчиков, тогда и понадобится id.
USER_ID = "founder"


class Message(BaseModel):
    text: str
    persona: str | None = None


@router.get("/history")
def history(limit: int = 100, _=Depends(auth)):
    """Переписка этого канала целиком. Телеграмная сюда не подмешивается.

    Читаем полную ленту, а не буфер для промпта: тот обрезан до 600 символов
    на реплику, и длинные ответы обрывались на полуслове.
    """
    messages = [
        {**m, "text": strip_markdown(m["text"]) if m.get("role") == "assistant" else m["text"]}
        for m in chat_log.recent(CHANNEL, USER_ID, limit=limit)
    ]
    return {"messages": messages}


@router.post("/message")
async def send(req: Message, _=Depends(auth)):
    """Принимает сообщение, возвращает ответ и имя ответившей персоны."""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Пустое сообщение")

    service = get_conversation_service()
    try:
        reply = await service.handle(
            channel=CHANNEL, user_id=USER_ID, text=text, persona=req.persona
        )
    except Exception as e:
        # Причина нужна человеку на экране: «что-то пошло не так» бесполезно
        logger.exception("Веб-чат не смог ответить")
        raise HTTPException(status_code=502, detail=str(e))

    thread = dialog_history.recent(CHANNEL, USER_ID)
    persona = next(
        (m.get("persona") for m in reversed(thread) if m.get("role") == "assistant"),
        "",
    )
    # Разметку не показываем: в чате она видна как мусор, а голосом
    # читается вслух названиями символов
    return {"reply": strip_markdown(reply), "persona": persona}


@router.post("/reset")
def reset(_=Depends(auth)):
    """Забыть нить разговора. Память фактов и заметки не трогаются."""
    removed = dialog_history.clear(CHANNEL, USER_ID)
    chat_log.clear(CHANNEL, USER_ID)
    return {"removed": removed}
