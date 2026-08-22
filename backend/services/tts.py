"""Синтез речи со сменным движком.

Фаундер просит голос — мужской или женский — и понимает, что для
коммерческого контура понадобится платный движок. Поэтому движок здесь
сменный с самого начала: переход на другой — это строка в .env, а не
переписывание системы.

Движки:
  edge      — нейронные голоса Microsoft Edge, бесплатно, ничего не весит.
              Годится для личного пользования; для коммерческого продукта
              это недокументированный чужой сервис, и на нём останавливаться
              нельзя.
  omnivoice — локальная модель, ничего не уходит наружу. Требует torch и
              несколько гигабайт на диске.
  eleven    — ElevenLabs, платно по символам. Для коммерческого контура.

Ни один движок не включён по умолчанию: голос стоит денег или трафика, и
включать его должен человек.
"""
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator

from ..core.config import settings

logger = logging.getLogger(__name__)


class VoiceUnavailable(RuntimeError):
    """Голос не настроен или движок недоступен. Причина — в тексте."""


@dataclass
class Voice:
    id: str
    label: str
    gender: str


# Голоса перечислены по движкам: человеку в интерфейсе нужен выбор
# «мужской/женский», а не строка вида ru-RU-DmitryNeural
EDGE_VOICES = [
    Voice("ru-RU-DmitryNeural", "Дмитрий", "male"),
    Voice("ru-RU-SvetlanaNeural", "Светлана", "female"),
    Voice("en-US-GuyNeural", "Guy", "male"),
    Voice("en-US-AriaNeural", "Aria", "female"),
]

ENGINES = ("none", "edge", "omnivoice", "eleven")

# Отдельный процесс в своём venv (voice_engine/.venv) — держит модель в
# памяти. Зависимости OmniVoice (torch, transformers, gradio) конфликтуют
# с версиями FastAPI/Starlette бэкенда, смешивать в один venv нельзя (уже
# один раз сломало тест). Поднимается вместе с остальным через start_all.ps1.
OMNIVOICE_SERVER_URL = os.getenv("OMNIVOICE_SERVER_URL", "http://127.0.0.1:8421")


def engine_name() -> str:
    name = (os.getenv("NEXUS_TTS_ENGINE", "") or "none").strip().lower()
    return name if name in ENGINES else "none"


def default_voice() -> str:
    return os.getenv("NEXUS_TTS_VOICE", "") or EDGE_VOICES[0].id


def is_enabled() -> bool:
    return engine_name() != "none"


def _rate_for(pace: int) -> str:
    """Ползунок «темп» (0..10, 5 — обычная скорость edge-tts) в проценты edge-tts.

    Диапазон -30%..+30% — за его пределами голос уже разваливается на слух.
    """
    percent = max(-30, min(30, (int(pace) - 5) * 6))
    return f"{percent:+d}%"


def list_voices() -> list[dict]:
    if engine_name() == "edge":
        return [v.__dict__ for v in EDGE_VOICES]
    return []


def status() -> dict:
    """Что включено и чего не хватает — без гадания на экране."""
    name = engine_name()
    detail = {
        "none": "голос выключен: NEXUS_TTS_ENGINE не задан",
        "edge": "нейронные голоса Microsoft Edge, бесплатно",
        "omnivoice": "локальная модель, ничего не уходит наружу",
        "eleven": "ElevenLabs, оплата по символам",
    }[name]

    ready = True
    if name == "edge":
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            ready = False
            detail = "движок edge выбран, но пакет edge-tts не установлен"
    elif name == "omnivoice":
        ready, detail = _omnivoice_server_status()
    elif name == "eleven":
        ready = bool(os.getenv("ELEVENLABS_API_KEY", ""))
        if not ready:
            detail = "движок eleven выбран, но нет ELEVENLABS_API_KEY"

    return {
        "engine": name,
        "enabled": name != "none",
        "ready": ready and name != "none",
        "detail": detail,
        "voice": default_voice(),
        "voices": list_voices(),
    }


async def synthesize(text: str, voice: str | None = None) -> Path:
    """Озвучивает текст, возвращает путь к файлу.

    Файл кладётся во временную папку артефактов: озвучка — мусор процесса,
    а не то, что человек будет искать в своих файлах.
    """
    from .textclean import for_speech

    # Синтезатор читает разметку вслух: «звёздочка звёздочка автохоткей».
    # Чистим до всего остального, включая подсчёт длины
    text = for_speech(text or "")
    if not text:
        raise ValueError("Нечего озвучивать")

    name = engine_name()
    if name == "none":
        raise VoiceUnavailable(
            "Голос выключен. Включается в .env: NEXUS_TTS_ENGINE=edge"
        )

    # Длинную простыню незачем гонять целиком: слушать её всё равно никто
    # не будет, а трафик и деньги расходуются
    limit = int(os.getenv("NEXUS_TTS_MAX_CHARS", "1200"))
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"

    if name == "edge":
        from .personas import get_character

        rate = _rate_for(get_character().get("pace", 5))
        return await _edge(text, voice or default_voice(), rate)
    if name == "omnivoice":
        return await _omnivoice(text)
    if name == "eleven":
        raise VoiceUnavailable("Движок eleven ещё не подключён")
    raise VoiceUnavailable(f"Неизвестный движок: {name}")


async def _edge(text: str, voice: str, rate: str = "+0%") -> Path:
    try:
        import edge_tts
    except ImportError as e:
        raise VoiceUnavailable("Пакет edge-tts не установлен: pip install edge-tts") from e

    from . import artifacts

    # Голос и темп входят в имя файла: тот же текст другой скоростью — это
    # другая запись, иначе она молча затирает предыдущую
    out = artifacts.temp_dir() / f"voice_{voice}_{rate}_{abs(hash(text)) % 10**8}.mp3"
    try:
        await edge_tts.Communicate(text, voice, rate=rate).save(str(out))
    except Exception as e:
        # Движок ходит в сеть — обрыв связи не должен выглядеть как поломка
        raise VoiceUnavailable(f"Озвучка не удалась: {e}") from e

    logger.info("Озвучено %d символов голосом %s", len(text), voice)
    return out


def prepare_edge_stream(text: str, voice: str | None = None):
    """Готовит потоковый синтез edge-tts — всё, что может сломаться СРАЗУ
    (пустой текст, движок не edge, пакет не установлен), проверяется здесь,
    синхронно с точки зрения вызывающего, чтобы HTTP-ручка успела ответить
    нормальным кодом ошибки до того, как уйдёт первый байт потока.

    19.08.2026, найдено фаундером вживую: пауза до нескольких секунд между
    вопросом и голосовым ответом — `synthesize()` ждёт, пока edge-tts
    синтезирует и сохранит ВЕСЬ файл на диск, и только потом отдаёт его
    браузеру целиком. `Communicate.stream()` в самой библиотеке отдаёт
    куски по мере готовности — этот путь просто раньше не использовался.
    Пока только для edge: у omnivoice/eleven стриминг не подключён.
    """
    from .textclean import for_speech

    text = for_speech(text or "")
    if not text:
        raise ValueError("Нечего озвучивать")

    if engine_name() != "edge":
        raise VoiceUnavailable("Потоковая озвучка пока умеет только движок edge")

    try:
        import edge_tts
    except ImportError as e:
        raise VoiceUnavailable("Пакет edge-tts не установлен: pip install edge-tts") from e

    from .personas import get_character

    rate = _rate_for(get_character().get("pace", 5))
    limit = int(os.getenv("NEXUS_TTS_MAX_CHARS", "1200"))
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"

    logger.info("Потоковая озвучка %d символов голосом %s", len(text), voice or default_voice())
    return edge_tts.Communicate(text, voice or default_voice(), rate=rate)


async def stream_chunks(communicate) -> AsyncGenerator[bytes, None]:
    """Байты аудио по мере готовности — то, ради чего весь этот путь.

    Сеть может оборваться на середине потока — здесь это не ловится
    намеренно: к этому моменту HTTP-ручка уже отправила заголовки со
    статусом 200, изменить код ответа больше нельзя, ловит и логирует
    вызывающая сторона (см. backend/api/voice.py).
    """
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]


def _omnivoice_server_status() -> tuple[bool, str]:
    """Жив ли сервер voice_engine/server.py и загружена ли в нём модель.

    Синхронный HTTP-запрос: status() дёргают из простых, не-async мест
    (например, /api/voice/status), заводить событийный цикл ради проверки
    не стоит — сам запрос локальный и мгновенный.
    """
    import httpx

    try:
        with httpx.Client(timeout=1.0) as client:
            r = client.get(f"{OMNIVOICE_SERVER_URL}/health")
        r.raise_for_status()
        if r.json().get("ready"):
            return True, "локальная модель, ничего не уходит наружу"
        return False, "сервер запущен, модель ещё грузится"
    except httpx.ConnectError:
        return False, (
            f"сервер не отвечает на {OMNIVOICE_SERVER_URL} — "
            "запустить: voice_engine/.venv/Scripts/python.exe voice_engine/server.py"
        )
    except Exception as e:
        return False, f"сервер omnivoice не отвечает: {e}"


async def _omnivoice(text: str) -> Path:
    """Синтез через локальный сервер voice_engine/server.py (свой venv,
    модель CC-BY-NC — только для личного использования, не для клиентских
    продуктов, см. комментарий в шапке файла)."""
    import httpx

    from . import artifacts

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{OMNIVOICE_SERVER_URL}/synthesize",
                json={"text": text, "language": "ru"},
            )
    except httpx.ConnectError as e:
        raise VoiceUnavailable(
            f"Сервер omnivoice не запущен на {OMNIVOICE_SERVER_URL}. "
            "Запускается вместе с остальным через start_all.ps1."
        ) from e
    except httpx.TimeoutException as e:
        raise VoiceUnavailable("Синтез omnivoice не уложился в минуту") from e

    if r.status_code != 200:
        detail = r.json().get("error", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
        raise VoiceUnavailable(f"Синтез omnivoice не удался: {detail}")

    out = artifacts.temp_dir() / f"voice_omnivoice_{abs(hash(text)) % 10**8}.wav"
    out.write_bytes(r.content)
    logger.info("Озвучено %d символов движком omnivoice", len(text))
    return out
