"""Voice API — озвучка ответов (PR-24) и распознавание речи (19.08.2026).

Речь наружу отдаётся файлом: браузер играет его сам, без потоков и
websocket'ов. Этого достаточно, чтобы услышать Джарвиса, и не тянет за
собой инфраструктуру, которую потом дорого чинить.

Распознавание речи внутрь — тем же путём, что уже год живёт для голосовых
Telegram (llm.transcribe_audio через Gemini). Понадобилось 19.08.2026: в
плавающем виджете (Electron) браузерный webkitSpeechRecognition не работает
в принципе — это облачная служба Google, которая проверяет API-ключ,
зашитый только в официальную сборку Chrome, а Electron его не имеет.
Симптом на экране фаундера — «Распознавание не смогло выйти в сеть»
(браузер честно вернул ошибку сети). Обойти нельзя, только заменить путь:
пишем звук в браузере, шлём файлом сюда, транскрибируем через Gemini —
то же самое, что уже работает у Hermes в Telegram.
"""
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from ..core.auth import _load_token, get_token_dep
from ..services import tts
from ..services.conversation import get_conversation_service
from ..services.llm import TranscriptionUnavailable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])
auth = get_token_dep()


def _verify_query_token(token: str | None = Query(None)) -> bool:
    """Проверка токена из строки запроса — отдельная от обычного HTTPBearer
    (`auth` выше). `<audio src="...">` физически не умеет слать заголовок
    Authorization, поэтому для потоковой озвучки токен идёт в самом URL.
    Используется ТОЛЬКО в /say-stream — остальные ручки как были, на
    HTTPBearer, это их не ослабляет."""
    stored = _load_token()
    if not stored:
        return True
    if token != stored:
        raise HTTPException(status_code=401, detail="Invalid token")
    return True


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

    # Тип берём из самого файла, а не зашиваем. «audio/mpeg + voice.mp3»
    # осталось со времён edge-tts, а Piper (движок по умолчанию с
    # 24.08.2026) отдаёт WAV — ответ врал про формат. Браузер это прощает,
    # он нюхает содержимое; сохранённый файл получил бы неверное
    # расширение. Замечено 25.08.2026 при переносе голосов.
    wav = path.suffix.lower() == ".wav"
    return FileResponse(
        path,
        media_type="audio/wav" if wav else "audio/mpeg",
        filename="voice.wav" if wav else "voice.mp3",
    )


@router.get("/say-stream")
async def say_stream(text: str, voice: str | None = None, _=Depends(_verify_query_token)):
    """Тот же синтез, что /say, но для edge байты уходят браузеру по мере
    готовности, а не после того, как весь ответ синтезирован целиком —
    фаундер нашёл вживую 19.08.2026, что пауза перед голосовым ответом
    доходила до нескольких секунд. GET, не POST: <audio src> сам грузит
    ресурс прогрессивно, без JS-обёртки вокруг blob, которая ждала бы весь
    ответ так же, как раньше.

    OmniVoice/eleven по кускам отдавать не умеют (OmniVoice генерирует весь
    звук одним проходом, дробить нечего) — для них тот же URL отдаёт файл
    целиком, одним куском в StreamingResponse. Один адрес для фронтенда
    независимо от того, какой движок сейчас включён в .env — ему не нужно
    об этом знать (см. speakStreamUrl() в api.ts).
    """
    if tts.engine_name() == "edge":
        try:
            communicate = tts.prepare_edge_stream(text, voice)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except tts.VoiceUnavailable as e:
            raise HTTPException(status_code=503, detail=str(e))

        async def gen():
            try:
                async for piece in tts.stream_chunks(communicate):
                    yield piece
            except Exception:
                logger.exception("Поток озвучки оборвался на середине")

        return StreamingResponse(gen(), media_type="audio/mpeg")

    try:
        path = await tts.synthesize(text, voice)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except tts.VoiceUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))

    media_type = "audio/wav" if path.suffix.lower() == ".wav" else "audio/mpeg"
    data = path.read_bytes()

    async def whole_file():
        yield data

    return StreamingResponse(whole_file(), media_type=media_type)


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), _=Depends(auth)):
    """Распознаёт голос из присланного аудиофайла (webm из браузера)."""
    llm = get_conversation_service().llm
    suffix = Path(file.filename or "voice.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        text = await llm.transcribe_audio(tmp_path)
    except TranscriptionUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("Распознавание речи не удалось")
        raise HTTPException(status_code=502, detail=f"Распознавание не удалось: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return {"text": text}
