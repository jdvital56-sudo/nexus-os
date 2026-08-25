# -*- coding: utf-8 -*-
"""Голос Piper один на всю машину — общий сервис для любого проекта.

25.08.2026, по прямой просьбе фаундера «голос Piper глобально на все
проекты». К этому моменту локальный Piper был написан ДВАЖДЫ и по-разному:
в Nexus OS (`backend/services/tts.py`, модель в памяти бэкенда) и в
Holovant (`apps/web/voice-worker/piper_worker.py`, отдельный процесс с
протоколом по stdin). Оба работают, но каждая новая программа означала бы
третью копию — вместе с третьим разом, когда кто-то заново напорется на
кириллицу в путях espeak.

Поэтому голос вынесен в отдельный сервис. Он держит модель в памяти один
раз на всю машину, а любой проект обращается к нему по HTTP: три строки
на любом языке вместо копии синтезатора. Модели (~60 МБ на голос) лежат
рядом в `piper_voices/` и в git не хранятся.

  GET  /health           жив ли, какой голос, сколько грузился
  GET  /voices           какие голоса реально скачаны
  POST /say    {text}    -> WAV байтами, звук проигрывает вызывающий
  POST /speak  {text}    -> проиграть здесь же, на колонках этой машины

Почему две ручки, а не одна. `/say` нужен браузеру и мобильному клиенту:
звук должен звучать у пользователя. `/speak` нужен скриптам и терминалу —
там некому проигрывать WAV, а сказать вслух надо; это же делает голос
доступным из любого места, где есть curl, без единой строки звукового кода.

Отдельный процесс, а не часть бэкенда Nexus OS, намеренно: голос нужен и
когда Nexus OS не поднят, а держать одну и ту же модель в памяти дважды
незачем.
"""
import argparse
import ctypes
import io
import logging
import os
import sys
import time
import wave
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("piper-server")


def _voices_dir() -> Path:
    """Где лежат модели голосов.

    Порядок неслучаен. Голоса — машинные данные, а не код проекта: одна и
    та же модель нужна всем программам сразу, и хранить её копию в каждом
    рабочем дереве значит держать по 180 МБ на дерево и получить сервис,
    который зависит от того, откуда его запустили. Поэтому основное место —
    общее `~/.nexsys/piper_voices`, рядом с остальными общими данными
    Nexus OS. Папка рядом со скриптом осталась запасной: там голоса лежали
    до 25.08.2026, и старые установки не должны онеметь после обновления.
    """
    override = os.getenv("PIPER_VOICES_DIR", "")
    if override:
        return Path(override)
    shared = Path.home() / ".nexsys" / "piper_voices"
    if any(shared.glob("*.onnx")):
        return shared
    return Path(__file__).resolve().parent / "piper_voices"


VOICES_DIR = _voices_dir()

# Голос по умолчанию — тот же, что уже выбран в Nexus OS: система должна
# звучать одинаково, из какой бы программы ни говорила.
DEFAULT_VOICE = os.getenv("PIPER_VOICE", "ru_RU-dmitri-medium")

# Порт: 8420 занят бэкендом Nexus OS, 8421 — OmniVoice, 8422 — слово-
# будильник. Берём следующий свободный и фиксируем его здесь, чтобы
# клиенты не гадали.
DEFAULT_PORT = int(os.getenv("PIPER_PORT", "8424"))

app = FastAPI(title="Piper Voice", docs_url=None, redoc_url=None)

_voices: dict[str, object] = {}
_load_seconds: float = 0.0


def _short_path(path: Path | str) -> str:
    """Короткое DOS-имя (8.3) пути.

    Нативный espeak-ng внутри Piper не открывает пути с кириллицей, а имя
    пользователя Windows у фаундера — «Вадим». Ровно эта ловушка уже
    ловила Vosk (19.08.2026) и Piper в двух проектах; здесь она решается
    один раз и для всех.
    """
    if os.name != "nt":
        return str(path)
    buf = ctypes.create_unicode_buffer(1024)
    written = ctypes.windll.kernel32.GetShortPathNameW(str(Path(path).resolve()), buf, 1024)
    return buf.value if written else str(path)


def available_voices() -> list[str]:
    """Только реально скачанные: обещать голос, которого нет на диске,
    значит отдать 500 тому, кто его выберет."""
    return sorted(p.stem for p in VOICES_DIR.glob("*.onnx"))


def load_voice(name: str):
    """Модель в память. Повторный вызов с тем же голосом — бесплатный.

    Держим все запрошенные голоса разом: их три по 60 МБ, а выгружать и
    грузить заново стоило бы 4.5 секунды на каждое переключение.
    """
    global _load_seconds

    if name in _voices:
        return _voices[name]

    model = VOICES_DIR / f"{name}.onnx"
    if not model.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Голос «{name}» не скачан. Есть: {', '.join(available_voices()) or 'ни одного'}",
        )

    import piper
    from piper import PiperVoice

    # Путь к данным espeak — только короткий (см. _short_path выше). Саму
    # модель грузим полным путём: её читает Python, ему кириллица не мешает.
    os.environ["ESPEAK_DATA_PATH"] = _short_path(Path(piper.__file__).parent / "espeak-ng-data")

    started = time.time()
    voice = PiperVoice.load(str(model.resolve()))
    _load_seconds = time.time() - started
    _voices[name] = voice
    logger.info("Голос %s загружен за %.2f с", name, _load_seconds)
    return voice


def synthesize(text: str, voice_name: str) -> bytes:
    """WAV в память, без временных файлов.

    Файла на диске здесь не нужно никому: браузер получает байты потоком,
    а `/speak` проигрывает их сам. Отсутствие файла заодно снимает вопрос,
    кто и когда его удалит.
    """
    voice = load_voice(voice_name)
    buffer = io.BytesIO()
    # wave.open требует объект с seek/tell — BytesIO это умеет, в отличие
    # от сетевого потока, поэтому синтез идёт в память целиком.
    with wave.open(buffer, "wb") as handle:
        voice.synthesize_wav(text, handle)
    return buffer.getvalue()


class Speech(BaseModel):
    text: str
    voice: str | None = None


@app.get("/health")
def health() -> dict:
    return {
        "ready": bool(_voices),
        "voice": DEFAULT_VOICE,
        "voices": available_voices(),
        "loaded": sorted(_voices),
        "load_seconds": round(_load_seconds, 2),
    }


@app.get("/voices")
def voices() -> dict:
    return {"voices": available_voices(), "default": DEFAULT_VOICE}


@app.post("/say")
def say(req: Speech) -> Response:
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Нечего озвучивать")
    started = time.time()
    audio = synthesize(text, req.voice or DEFAULT_VOICE)
    logger.info("Озвучено %d символов за %.2f с", len(text), time.time() - started)
    # no-store: та же фраза с другим голосом — другой звук, а кэш браузера
    # ключуется по URL, который у POST один на всё.
    return Response(content=audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})


@app.post("/speak")
def speak(req: Speech) -> dict:
    """Сказать вслух здесь же, на колонках этой машины.

    Через winsound из стандартной библиотеки: он умеет ровно WAV из памяти
    и ровно это здесь и нужно — тянуть звуковую библиотеку ради одной
    функции незачем.

    Проигрывание — в отдельном потоке. Очевидный `SND_ASYNC` тут не
    работает: winsound не умеет асинхронно ИЗ ПАМЯТИ и падает с «Cannot
    play asynchronously from memory» (найдено первым же живым вызовом
    25.08.2026). Писать ради флага временный файл незачем — достаточно
    отпустить ручку, а звук доиграет поток. Заодно это ровно то поведение,
    которого ждёшь: winsound держит один звук за раз, и новая фраза
    обрывает предыдущую, как перебивание голосом в Nexus OS.
    """
    import threading
    import winsound

    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Нечего озвучивать")

    started = time.time()
    audio = synthesize(text, req.voice or DEFAULT_VOICE)
    seconds = round(time.time() - started, 2)

    threading.Thread(
        target=winsound.PlaySound,
        args=(audio, winsound.SND_MEMORY),
        daemon=True,
    ).start()

    logger.info("Сказано вслух %d символов, синтез %.2f с", len(text), seconds)
    return {"ok": True, "seconds": seconds, "chars": len(text)}


@app.post("/stop")
def stop() -> dict:
    """Замолчать немедленно — то же, что «стоп» голосом в Nexus OS."""
    import winsound

    winsound.PlaySound(None, winsound.SND_PURGE)
    return {"ok": True}


@app.on_event("startup")
def warm_up() -> None:
    """Первый синтез поднимает espeak и стоит несколько секунд. Заплатить
    их здесь — значит не заставлять ждать первую живую фразу."""
    if not available_voices():
        logger.error("В %s нет ни одного голоса — сервис бесполезен", VOICES_DIR)
        return
    name = DEFAULT_VOICE if DEFAULT_VOICE in available_voices() else available_voices()[0]
    started = time.time()
    synthesize("Готов", name)
    logger.info("Прогрев голосом %s занял %.2f с", name, time.time() - started)


def main() -> int:
    parser = argparse.ArgumentParser(description="Общий голос Piper для всех проектов")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
