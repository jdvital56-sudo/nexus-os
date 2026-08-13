"""Тесты распознавания речи (PR-6)."""
import pytest

from backend.services.llm import (
    LLMService,
    TranscriptionUnavailable,
    guess_audio_mime,
)


def test_telegram_voice_mime_is_ogg():
    """Голосовые Telegram приходят в ogg — раньше уходили как audio/mpeg."""
    assert guess_audio_mime("/tmp/voice_1.ogg") == "audio/ogg"
    assert guess_audio_mime("/tmp/voice_1.oga") == "audio/ogg"


def test_other_formats_are_recognised():
    assert guess_audio_mime("note.mp3") == "audio/mpeg"
    assert guess_audio_mime("note.wav") == "audio/wav"


def test_unknown_extension_falls_back():
    assert guess_audio_mime("note.unknown") == "audio/mpeg"


@pytest.mark.asyncio
async def test_transcription_without_key_says_so_honestly():
    """Без ключа — понятная причина, а не молчаливое падение."""
    svc = LLMService()
    svc.gemini_api_key = ""

    with pytest.raises(TranscriptionUnavailable) as exc:
        await svc.transcribe_audio("/tmp/voice.ogg")

    assert "GEMINI_API_KEY" in str(exc.value)


@pytest.mark.asyncio
async def test_transcription_with_key_asks_gemini(monkeypatch):
    svc = LLMService()
    svc.gemini_api_key = "test-key"
    seen = {}

    async def fake_audio(audio_path: str, prompt: str, max_tokens: int) -> str:
        seen["path"] = audio_path
        seen["prompt"] = prompt
        return "расшифрованный текст"

    monkeypatch.setattr(svc, "_gemini_audio", fake_audio)

    result = await svc.transcribe_audio("/tmp/voice.ogg")

    assert result == "расшифрованный текст"
    assert seen["path"] == "/tmp/voice.ogg"
    assert "дословно" in seen["prompt"]


# --- Ключ Gemini не подхватывался из .env (найдено 2026-08-12) ---


def test_short_env_name_wins(monkeypatch):
    """В .env ключ называется GEMINI_API_KEY, а код читал только
    NEXSYS_GEMINI_API_KEY — вписанный ключ молча не работал."""
    from backend.core.config import env_any

    monkeypatch.setenv("GEMINI_API_KEY", "короткое")
    monkeypatch.setenv("NEXSYS_GEMINI_API_KEY", "длинное")

    assert env_any("GEMINI_API_KEY", "NEXSYS_GEMINI_API_KEY") == "короткое"


def test_long_env_name_still_works(monkeypatch):
    """Старое имя не ломаем: у кого прописано NEXSYS_GEMINI_API_KEY."""
    from backend.core.config import env_any

    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("NEXSYS_GEMINI_API_KEY", "длинное")

    assert env_any("GEMINI_API_KEY", "NEXSYS_GEMINI_API_KEY") == "длинное"


def test_no_key_gives_empty(monkeypatch):
    from backend.core.config import env_any

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("NEXSYS_GEMINI_API_KEY", raising=False)

    assert env_any("GEMINI_API_KEY", "NEXSYS_GEMINI_API_KEY") == ""
