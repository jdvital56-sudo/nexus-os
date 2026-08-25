# -*- coding: utf-8 -*-
"""Клиент общего голоса Piper — скопировать в любой Python-проект.

Файл намеренно самодостаточный: ни одного импорта из Nexus OS, только
стандартная библиотека. Смысл общего сервиса в том, чтобы новый проект
получал голос копированием одного файла, а не подключением чужого пакета.

    from client import say, speak

    speak("Сборка прошла")          # сказать вслух на этой машине
    wav = say("Привет")             # WAV байтами — отдать браузеру и т.п.

Сервис не поднят — функции поднимают VoiceUnavailable с адресом и командой
запуска в тексте, а не молча возвращают тишину: тишину невозможно отличить
от «нечего сказать».
"""
import json
import os
import urllib.error
import urllib.request

SERVER = os.getenv("PIPER_SERVER", "http://127.0.0.1:8424")

# Синтез редко занимает больше секунды, но первая фраза после запуска ждёт
# загрузки модели — там счёт идёт на десяток секунд.
TIMEOUT = float(os.getenv("PIPER_TIMEOUT", "30"))


class VoiceUnavailable(RuntimeError):
    """Сервис голоса недоступен. Причина — в тексте ошибки."""


def _post(path: str, payload: dict) -> bytes:
    request = urllib.request.Request(
        f"{SERVER}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read()
    except urllib.error.HTTPError as e:
        raise VoiceUnavailable(f"Голос ответил {e.code}: {e.read().decode('utf-8', 'replace')}") from e
    except urllib.error.URLError as e:
        raise VoiceUnavailable(
            f"Сервис голоса не отвечает на {SERVER} ({e.reason}). "
            "Запускается вместе с остальным через start_all.ps1, вручную: "
            "python voice_engine/piper_server.py"
        ) from e


def say(text: str, voice: str | None = None) -> bytes:
    """Озвучивает текст и возвращает WAV байтами."""
    payload: dict = {"text": text}
    if voice:
        payload["voice"] = voice
    return _post("/say", payload)


def speak(text: str, voice: str | None = None) -> dict:
    """Говорит вслух на колонках этой машины. Не ждёт конца фразы."""
    payload: dict = {"text": text}
    if voice:
        payload["voice"] = voice
    return json.loads(_post("/speak", payload))


def shut_up() -> None:
    """Оборвать текущую фразу."""
    _post("/stop", {})


def health() -> dict:
    try:
        with urllib.request.urlopen(f"{SERVER}/health", timeout=5) as response:
            return json.loads(response.read())
    except urllib.error.URLError as e:
        raise VoiceUnavailable(f"Сервис голоса не отвечает на {SERVER} ({e.reason})") from e
