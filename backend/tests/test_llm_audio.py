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
