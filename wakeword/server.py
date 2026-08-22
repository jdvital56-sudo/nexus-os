"""Локальный сервер слова-будильника «Джарвис» — офлайн, для плавающего
виджета (Electron), 19.08.2026.

Почему отдельный процесс, не часть backend/. Браузерное распознавание речи
(webkitSpeechRecognition) в Electron физически не работает — облачная
служба Google проверяет ключ, зашитый только в настоящую сборку Chrome
(см. frontend/src/lib/speech.ts). Фаундер спросил фоновое «слушать Джарвис»
даже когда виджет свёрнут — единственный путь без постоянной отправки
звука на сервер (что стоило бы денег непрерывно, 24/7, а не только когда
реально позвали) — офлайн-движок прямо на машине. Vosk выбран вместо
Picovoice/openWakeWord: не нужен аккаунт/ключ, и у него есть готовая
русская модель — «Джарвис» не английское слово, кастомно обучать чужой
движок под него было бы отдельным исследовательским проектом.

Микрофон слушает Vosk (маленькая русская модель, ~45 МБ, полностью
локально, CPU, без GPU). Сервер НЕ решает сам, что такое «слово-будильник»
— просто транскрибирует и рассылает текст всем подключённым клиентам по
WebSocket. Вся логика «это было имя, а не случайное слово» и «заглушить
на время своей же озвучки, чтобы не отвечать самому себе» — на стороне
клиента (frontend/src/lib/speech.ts, тот же WAKE-регексп и тот же приём
mute/unmute, что у браузерного listenForWakeWord) — один источник правды
для распознавания имени, не дублируется здесь.

Отдельный процесс, не поток внутри backend/: FastAPI не должен зависеть от
постоянно открытого микрофона, а этот процесс не должен падать вместе с
перезапуском бэкенда при каждой правке .py (backend перезапускается вручную
часто, см. nexus-os-dev-environment).
"""
import asyncio
import ctypes
import json
import logging
import queue
import sys
from pathlib import Path

import sounddevice as sd
import websockets
from vosk import KaldiRecognizer, Model, SetLogLevel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("wakeword")

SetLogLevel(-1)  # Vosk-овский C++ лог очень болтливый, глушим

MODEL_DIR = Path(__file__).parent / "model"
SAMPLE_RATE = 16000
PORT = 8422

_clients: "set" = set()
_audio_queue: "queue.Queue[bytes]" = queue.Queue()


def _short_path(path: Path) -> str:
    """Vosk (нативная C++-библиотека) не умеет читать пути с кириллицей —
    у фаундера имя пользователя Windows «Вадим», и любой путь внутри его
    профиля ломает Model() с невнятной ошибкой «Folder ... does not
    contain model files», хотя файлы там реально есть (найдено 19.08.2026
    методом проб). Короткое DOS-имя (8.3) — тот же каталог, ASCII-алиас,
    который Windows создаёт автоматически для каждой папки — Vosk его
    читает нормально, ничего дополнительно включать не нужно.
    """
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, 260)
    return buf.value or str(path)


def _on_audio(indata, frames, time_info, status) -> None:
    """Колбэк sounddevice — свой поток, не asyncio. Очередь — мост между
    ним и циклом распознавания ниже."""
    if status:
        logger.warning("Статус аудиопотока: %s", status)
    _audio_queue.put(bytes(indata))


async def _broadcast(message: dict) -> None:
    if not _clients:
        return
    data = json.dumps(message, ensure_ascii=False)
    dead = set()
    for ws in _clients:
        try:
            await ws.send(data)
        except websockets.ConnectionClosed:
            dead.add(ws)
    _clients.difference_update(dead)


async def _recognize_loop(model: Model) -> None:
    rec = KaldiRecognizer(model, SAMPLE_RATE)
    loop = asyncio.get_event_loop()
    while True:
        # queue.Queue.get блокирует поток исполнителя, не сам цикл событий
        data = await loop.run_in_executor(None, _audio_queue.get)
        if rec.AcceptWaveform(data):
            result = json.loads(rec.Result())
            text = (result.get("text") or "").strip()
            if text:
                logger.info("финал: %s", text)
                await _broadcast({"type": "final", "text": text})
        else:
            partial = json.loads(rec.PartialResult())
            text = (partial.get("partial") or "").strip()
            if text:
                await _broadcast({"type": "partial", "text": text})


async def _handle_client(websocket) -> None:
    _clients.add(websocket)
    logger.info("клиент подключился, всего: %d", len(_clients))
    try:
        await websocket.wait_closed()
    finally:
        _clients.discard(websocket)
        logger.info("клиент отключился, всего: %d", len(_clients))


async def main() -> None:
    if not MODEL_DIR.exists():
        logger.error(
            "Модель не найдена: %s — распаковать vosk-model-small-ru-0.22 в wakeword/model",
            MODEL_DIR,
        )
        sys.exit(1)

    logger.info("Гружу модель...")
    model = Model(_short_path(MODEL_DIR))
    logger.info("Модель готова, открываю микрофон")

    stream = sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=8000,
        dtype="int16",
        channels=1,
        callback=_on_audio,
    )
    stream.start()

    async with websockets.serve(_handle_client, "127.0.0.1", PORT):
        logger.info("Слушаю ws://127.0.0.1:%d — слово «Джарвис» ловит клиент", PORT)
        try:
            await _recognize_loop(model)
        finally:
            stream.stop()
            stream.close()


if __name__ == "__main__":
    asyncio.run(main())
