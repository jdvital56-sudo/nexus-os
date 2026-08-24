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

ENGINES = ("none", "piper", "edge", "omnivoice", "eleven")

# Голоса Piper — локальные файлы модели (.onnx) рядом с проектом.
# Скачиваются с huggingface.co/rhasspy/piper-voices, ~63 МБ на голос.
PIPER_VOICES = [
    Voice("ru_RU-dmitri-medium", "Дмитрий (локальный)", "male"),
    Voice("ru_RU-irina-medium", "Ирина (локальная)", "female"),
    Voice("ru_RU-ruslan-medium", "Руслан (локальный)", "male"),
    Voice("ru_RU-denis-medium", "Денис (локальный)", "male"),
]

PIPER_VOICES_DIR = Path(__file__).resolve().parents[2] / "voice_engine" / "piper_voices"

# Отдельный процесс в своём venv (voice_engine/.venv) — держит модель в
# памяти. Зависимости OmniVoice (torch, transformers, gradio) конфликтуют
# с версиями FastAPI/Starlette бэкенда, смешивать в один venv нельзя (уже
# один раз сломало тест). Поднимается вместе с остальным через start_all.ps1.
OMNIVOICE_SERVER_URL = os.getenv("OMNIVOICE_SERVER_URL", "http://127.0.0.1:8421")


def engine_name() -> str:
    name = (os.getenv("NEXUS_TTS_ENGINE", "") or "none").strip().lower()
    return name if name in ENGINES else "none"


def default_voice() -> str:
    stored = os.getenv("NEXUS_TTS_VOICE", "")
    if stored:
        return stored
    return PIPER_VOICES[0].id if engine_name() == "piper" else EDGE_VOICES[0].id


# 23.08.2026: фаундер попросил голос «более синтетичный, как у Железного
# человека», оставаясь на русском (выбрал сам из вариантов — английский
# акцент или платный ElevenLabs отклонены). У edge-tts нет отдельного
# «роботизированного» голоса для ru-RU (только Дмитрий/Светлана) — рычаг,
# который реально есть, это высота тона через SSML: ниже и ровнее пресета
# по умолчанию читается на слух более механически, ближе к ассистенту, чем
# к живому диктору. Настраиваемо через .env, чтобы можно было подстроить
# на слух, не трогая код.
def pitch_shift() -> str:
    return os.getenv("NEXUS_TTS_PITCH", "-8Hz")


def is_enabled() -> bool:
    return engine_name() != "none"


def _rate_for(pace: int) -> str:
    """Ползунок «темп» (0..10, 5 — обычная скорость edge-tts) в проценты edge-tts.

    Диапазон -30%..+30% — за его пределами голос уже разваливается на слух.
    """
    percent = max(-30, min(30, (int(pace) - 5) * 6))
    return f"{percent:+d}%"


def list_voices() -> list[dict]:
    name = engine_name()
    if name == "piper":
        # Только реально скачанные: показывать в выпадашке голос, которого
        # нет на диске, значит обещать то, что выберут и не получат.
        return [v.__dict__ for v in PIPER_VOICES if (PIPER_VOICES_DIR / f"{v.id}.onnx").is_file()]
    if name == "edge":
        return [v.__dict__ for v in EDGE_VOICES]
    return []


def status() -> dict:
    """Что включено и чего не хватает — без гадания на экране."""
    name = engine_name()
    detail = {
        "none": "голос выключен: NEXUS_TTS_ENGINE не задан",
        "piper": "локальный синтез на этом компьютере, без интернета",
        "edge": "нейронные голоса Microsoft Edge, бесплатно",
        "omnivoice": "локальная модель, ничего не уходит наружу",
        "eleven": "ElevenLabs, оплата по символам",
    }[name]

    ready = True
    if name == "piper":
        try:
            import piper  # noqa: F401
        except ImportError:
            ready = False
            detail = "движок piper выбран, но пакет piper-tts не установлен"
        else:
            downloaded = [v for v in PIPER_VOICES if (PIPER_VOICES_DIR / f"{v.id}.onnx").is_file()]
            if not downloaded:
                ready = False
                detail = f"движок piper выбран, но ни один голос не скачан в {PIPER_VOICES_DIR}"
            else:
                detail = f"локальный синтез, голосов скачано: {len(downloaded)}"
    elif name == "edge":
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

    if name == "piper":
        return await _piper(text, voice or default_voice())
    if name == "edge":
        from .personas import get_character

        rate = _rate_for(get_character().get("pace", 5))
        return await _edge(text, voice or default_voice(), rate, pitch_shift())
    if name == "omnivoice":
        return await _omnivoice(text)
    if name == "eleven":
        raise VoiceUnavailable("Движок eleven ещё не подключён")
    raise VoiceUnavailable(f"Неизвестный движок: {name}")


async def _edge(text: str, voice: str, rate: str = "+0%", pitch: str = "+0Hz") -> Path:
    try:
        import edge_tts
    except ImportError as e:
        raise VoiceUnavailable("Пакет edge-tts не установлен: pip install edge-tts") from e

    from . import artifacts

    # Голос, темп и высота тона входят в имя файла: тот же текст с другими
    # настройками — это другая запись, иначе она молча затирает предыдущую
    out = artifacts.temp_dir() / f"voice_{voice}_{rate}_{pitch}_{abs(hash(text)) % 10**8}.mp3"
    try:
        await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(out))
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
    return edge_tts.Communicate(text, voice or default_voice(), rate=rate, pitch=pitch_shift())


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


# === Piper: локальный синтез ===============================================
#
# 24.08.2026, по жалобе фаундера «отвечает через 15 секунд». Измерено, а не
# предположено: edge-tts (серверы Microsoft) отдавал первый байт звука за
# 2.4, 3.7 и 37.4 секунды в трёх замерах подряд — разброс не наш, а сетевой,
# и предсказать его нельзя. Piper считает на этом же процессоре: 0.41-0.66
# секунды, медиана 0.55 на восьми замерах. Плюс работает без интернета.
#
# Модель держим загруженной в память процесса: сама загрузка стоит 4.5
# секунды, платить их на каждую фразу было бы бессмысленно.
_piper_voice = None
_piper_voice_id: str | None = None


def _piper_short_path(path: Path | str) -> str:
    """Короткое DOS-имя (8.3) пути.

    Нативный espeak-ng внутри Piper не читает пути с кириллицей, а у
    фаундера имя пользователя Windows «Вадим» — падает с «Illegal byte
    sequence». Ровно та же ловушка, что уже ловила Vosk 19.08.2026
    (см. wakeword/server.py), и то же решение: Windows сама держит для
    каждой папки ASCII-алиас.
    """
    import ctypes

    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.kernel32.GetShortPathNameW(str(Path(path).resolve()), buf, 260)
    return buf.value or str(path)


def _piper_load(voice_id: str):
    """Модель в память. Повторный вызов с тем же голосом — бесплатный."""
    global _piper_voice, _piper_voice_id
    if _piper_voice is not None and _piper_voice_id == voice_id:
        return _piper_voice

    try:
        import piper
        from piper import PiperVoice
    except ImportError as e:
        raise VoiceUnavailable(
            "Пакет piper-tts не установлен: pip install piper-tts"
        ) from e

    model = PIPER_VOICES_DIR / f"{voice_id}.onnx"
    if not model.is_file():
        raise VoiceUnavailable(
            f"Голос {voice_id} не скачан. Файл ожидается здесь: {model}"
        )

    # Путь к данным espeak — только короткий (см. _piper_short_path выше).
    # Саму модель грузим полным путём: её читает Python, ему кириллица не мешает.
    os.environ["ESPEAK_DATA_PATH"] = _piper_short_path(
        Path(piper.__file__).parent / "espeak-ng-data"
    )

    _piper_voice = PiperVoice.load(str(model.resolve()))
    _piper_voice_id = voice_id
    logger.info("Piper: голос %s загружен в память", voice_id)
    return _piper_voice


async def _piper(text: str, voice_id: str) -> Path:
    """Синтез на этой же машине. Возвращает WAV — Piper отдаёт только его,
    а браузер играет WAV не хуже MP3."""
    import asyncio
    import wave

    from . import artifacts

    out = artifacts.temp_dir() / f"voice_{voice_id}_{abs(hash(text)) % 10**8}.wav"
    if out.is_file():
        return out

    def _run() -> None:
        v = _piper_load(voice_id)
        with wave.open(str(out), "wb") as wf:
            v.synthesize_wav(text, wf)

    # Синтез — счёт на процессоре, он блокирующий: без to_thread он бы
    # останавливал весь event loop бэкенда на полсекунды при каждой фразе.
    try:
        await asyncio.to_thread(_run)
    except VoiceUnavailable:
        raise
    except Exception as e:
        raise VoiceUnavailable(f"Piper не смог синтезировать речь: {e}") from e
    return out
