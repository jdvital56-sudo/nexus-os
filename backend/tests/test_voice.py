"""Голос со сменным движком (PR-24).

Главное, что проверяется: выключенный голос ведёт себя как выключенный, а
не как поломка, и смена движка — это настройка, а не правка кода.
"""
import pytest

from backend.services import tts


def test_voice_is_off_by_default(monkeypatch):
    """Голос стоит денег или трафика — включает его человек, не система."""
    monkeypatch.delenv("NEXUS_TTS_ENGINE", raising=False)

    assert tts.engine_name() == "none"
    assert tts.is_enabled() is False
    assert tts.status()["ready"] is False


def test_unknown_engine_falls_back_to_off(monkeypatch):
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "выдуманный")

    assert tts.engine_name() == "none"


@pytest.mark.asyncio
async def test_disabled_voice_explains_how_to_turn_on(monkeypatch):
    monkeypatch.delenv("NEXUS_TTS_ENGINE", raising=False)

    with pytest.raises(tts.VoiceUnavailable) as e:
        await tts.synthesize("привет")

    assert "NEXUS_TTS_ENGINE" in str(e.value)


@pytest.mark.asyncio
async def test_empty_text_is_refused(monkeypatch):
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "edge")

    with pytest.raises(ValueError):
        await tts.synthesize("   ")


@pytest.mark.asyncio
async def test_long_text_is_clipped(monkeypatch):
    """Простыню целиком никто не слушает, а трафик и деньги уходят."""
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "edge")
    monkeypatch.setenv("NEXUS_TTS_MAX_CHARS", "50")
    said: dict = {}

    async def fake_edge(text, voice):
        said["text"] = text
        said["voice"] = voice
        return "файл.mp3"

    monkeypatch.setattr(tts, "_edge", fake_edge)

    await tts.synthesize("слово " * 100)

    assert len(said["text"]) <= 51
    assert said["text"].endswith("…")


@pytest.mark.asyncio
async def test_engine_is_switched_by_setting(monkeypatch):
    """Переход на другой движок — строка в .env, а не правка кода."""
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "omnivoice")

    with pytest.raises(tts.VoiceUnavailable) as e:
        await tts.synthesize("привет")

    assert "omnivoice" in str(e.value)
    assert tts.status()["engine"] == "omnivoice"


def test_eleven_without_key_is_not_ready(monkeypatch):
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "eleven")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    state = tts.status()

    assert state["enabled"] is True
    assert state["ready"] is False
    assert "ELEVENLABS_API_KEY" in state["detail"]


def test_voices_have_gender(monkeypatch):
    """Человеку нужен выбор «мужской/женский», а не ru-RU-DmitryNeural."""
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "edge")

    genders = {v["gender"] for v in tts.list_voices()}

    assert {"male", "female"} <= genders


def test_api_reports_disabled_voice(client, monkeypatch):
    monkeypatch.delenv("NEXUS_TTS_ENGINE", raising=False)

    r = client.get("/api/voice/status")

    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_api_say_returns_503_when_off(client, monkeypatch):
    """Выключено — это не 500: человеку показывают причину, а не сбой."""
    monkeypatch.delenv("NEXUS_TTS_ENGINE", raising=False)

    r = client.post("/api/voice/say", json={"text": "привет"})

    assert r.status_code == 503
    assert "NEXUS_TTS_ENGINE" in r.json()["detail"]
