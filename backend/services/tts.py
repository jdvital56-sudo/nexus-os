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


def engine_name() -> str:
    name = (os.getenv("NEXUS_TTS_ENGINE", "") or "none").strip().lower()
    return name if name in ENGINES else "none"


def default_voice() -> str:
    return os.getenv("NEXUS_TTS_VOICE", "") or EDGE_VOICES[0].id


def is_enabled() -> bool:
    return engine_name() != "none"


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
        ready = False
        detail = "движок omnivoice ещё не подключён: нужны torch и веса модели"
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
    text = (text or "").strip()
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
        return await _edge(text, voice or default_voice())
    if name == "omnivoice":
        raise VoiceUnavailable(
            "Движок omnivoice ещё не подключён: нужны torch и веса модели, "
            "около 6 ГБ на диске"
        )
    if name == "eleven":
        raise VoiceUnavailable("Движок eleven ещё не подключён")
    raise VoiceUnavailable(f"Неизвестный движок: {name}")


async def _edge(text: str, voice: str) -> Path:
    try:
        import edge_tts
    except ImportError as e:
        raise VoiceUnavailable("Пакет edge-tts не установлен: pip install edge-tts") from e

    from . import artifacts

    # Голос входит в имя файла: один и тот же текст разными голосами — это
    # разные записи, иначе вторая молча затирает первую
    out = artifacts.temp_dir() / f"voice_{voice}_{abs(hash(text)) % 10**8}.mp3"
    try:
        await edge_tts.Communicate(text, voice).save(str(out))
    except Exception as e:
        # Движок ходит в сеть — обрыв связи не должен выглядеть как поломка
        raise VoiceUnavailable(f"Озвучка не удалась: {e}") from e

    logger.info("Озвучено %d символов голосом %s", len(text), voice)
    return out
