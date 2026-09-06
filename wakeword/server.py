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
import os
import queue
import sys
from pathlib import Path

import sounddevice as sd
import websockets
from vosk import KaldiRecognizer, Model, SetLogLevel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("wakeword")

SetLogLevel(-1)  # Vosk-овский C++ лог очень болтливый, глушим

def _model_dir() -> Path:
    """Где лежит модель Vosk.

    Порядок тот же и по той же причине, что у голосов Piper (см.
    `voice_engine/piper_server.py`): модель на 88 МБ — машинные данные, а не
    код проекта. Рабочих деревьев на этом репозитории бывает несколько, и
    копия модели в каждом не нужна никому; запущенный из дерева сервер
    молча не находил модель и не поднимался вовсе (07.09.2026).

    Папка рядом со скриптом остаётся запасной: там модель лежала раньше, и
    обновление не должно лишать будильника установку, где переезда не было.
    """
    override = os.getenv("VOSK_MODEL_DIR", "")
    if override:
        return Path(override)
    shared = Path.home() / ".nexsys" / "vosk_model"
    if shared.is_dir():
        return shared
    return Path(__file__).parent / "model"


MODEL_DIR = _model_dir()
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
                # Саму речь в лог НЕ пишем. Раньше здесь стояло
                # `logger.info("финал: %s", text)`, и за две с половиной
                # недели в wakeword_stderr.log осело 3580 расшифровок — 320 КБ
                # всего, что говорилось возле компьютера, обычным текстом и
                # навсегда. Это не было задумано: логи микрофона писались в
                # stderr как отладка, а превратились в бессрочную запись
                # разговоров. Фаундер согласился убрать 07.09.2026, когда
                # будильник включали в автозапуск.
                #
                # Диагностику это не ломает: чтобы понять «слышит ли он
                # вообще», достаточно знать, что распознавание случилось и
                # какой длины фраза. Что именно сказано — знает клиент,
                # которому текст и уходит.
                logger.info("распознано, символов: %d", len(text))
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
