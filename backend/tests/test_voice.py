"""Голос со сменным движком (PR-24).

Главное, что проверяется: выключенный голос ведёт себя как выключенный, а
не как поломка, и смена движка — это настройка, а не правка кода.
"""
import pytest

from backend.services import tts


class _FakeCommunicate:
    """Подменяет edge_tts.Communicate — тесты не должны реально стучаться
    в сервис Microsoft за звуком."""

    def __init__(self, text, voice, rate="+0%", pitch="+0Hz"):
        self.text = text
        self.voice = voice
        self.rate = rate
        self.pitch = pitch

    async def stream(self):
        # WordBoundary вперемешку с audio — как реально отдаёт edge-tts,
        # stream_chunks() обязан пропускать всё, что не "audio"
        yield {"type": "WordBoundary", "text": "привет", "offset": 0, "duration": 0.1}
        yield {"type": "audio", "data": b"chunk1"}
        yield {"type": "audio", "data": b"chunk2"}


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

    async def fake_edge(text, voice, rate="+0%", pitch="+0Hz"):
        said["text"] = text
        said["voice"] = voice
        said["rate"] = rate
        return "файл.mp3"

    monkeypatch.setattr(tts, "_edge", fake_edge)

    await tts.synthesize("слово " * 100)

    assert len(said["text"]) <= 51
    assert said["text"].endswith("…")


@pytest.mark.asyncio
async def test_engine_is_switched_by_setting(monkeypatch):
    """Переход на другой движок — строка в .env, а не правка кода.

    Сервер omnivoice реальный (см. voice_engine/), поэтому здесь он
    промокан — тест не должен зависеть от того, поднят ли он на машине,
    где запускаются тесты."""
    import httpx

    async def fake_post(self, url, **kwargs):
        raise httpx.ConnectError("connection refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "omnivoice")

    with pytest.raises(tts.VoiceUnavailable) as e:
        await tts.synthesize("привет")

    assert "omnivoice" in str(e.value) or "8421" in str(e.value)
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


# --- Темп речи: ползунок «pace» из характера, но только для звука (2026-08-12) ---


def test_rate_defaults_to_no_change():
    assert tts._rate_for(5) == "+0%"


def test_rate_is_clamped_within_thirty_percent():
    assert tts._rate_for(0) == "-30%"
    assert tts._rate_for(10) == "+30%"


@pytest.mark.asyncio
async def test_pace_reaches_the_edge_call(monkeypatch):
    """Ползунок «Темп речи» в Пантеоне должен реально влиять на озвучку."""
    from backend.services import personas as personas_svc

    monkeypatch.setenv("NEXUS_TTS_ENGINE", "edge")
    personas_svc.set_character({"pace": 0})
    said: dict = {}

    async def fake_edge(text, voice, rate="+0%", pitch="+0Hz"):
        said["rate"] = rate
        said["pitch"] = pitch
        return "файл.mp3"

    monkeypatch.setattr(tts, "_edge", fake_edge)

    await tts.synthesize("привет")

    assert said["rate"] == "-30%"


def test_pitch_shift_default_is_lower_than_natural():
    """23.08.2026: фаундер попросил более синтетичный голос, оставаясь на
    русском — понижение высоты тона по умолчанию, а не «+0Hz»."""
    assert tts.pitch_shift() == "-8Hz"


def test_pitch_shift_configurable_via_env(monkeypatch):
    monkeypatch.setenv("NEXUS_TTS_PITCH", "-15Hz")
    assert tts.pitch_shift() == "-15Hz"


# --- OmniVoice: отдельный процесс в своём venv, движок стучится к нему по HTTP ---


def test_omnivoice_status_when_server_is_down(monkeypatch):
    """Сервер не поднят — статус объясняет, чем его поднять, а не молчит."""
    import httpx

    def fake_get(self, url, **kwargs):
        raise httpx.ConnectError("connection refused", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "omnivoice")

    s = tts.status()

    assert s["ready"] is False
    assert "server.py" in s["detail"]


def test_omnivoice_status_when_model_still_loading(monkeypatch):
    import httpx

    def fake_get(self, url, **kwargs):
        return httpx.Response(200, json={"ready": False}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "omnivoice")

    s = tts.status()

    assert s["ready"] is False
    assert "грузится" in s["detail"]


def test_omnivoice_status_when_ready(monkeypatch):
    import httpx

    def fake_get(self, url, **kwargs):
        return httpx.Response(200, json={"ready": True}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "omnivoice")

    assert tts.status()["ready"] is True


@pytest.mark.asyncio
async def test_omnivoice_synthesize_saves_the_response(monkeypatch):
    import httpx

    async def fake_post(self, url, **kwargs):
        return httpx.Response(200, content=b"RIFF....WAVEfake", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "omnivoice")

    out = await tts.synthesize("привет")

    assert out.read_bytes() == b"RIFF....WAVEfake"


@pytest.mark.asyncio
async def test_omnivoice_synthesize_when_server_is_down(monkeypatch):
    import httpx

    async def fake_post(self, url, **kwargs):
        raise httpx.ConnectError("connection refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "omnivoice")

    with pytest.raises(tts.VoiceUnavailable) as e:
        await tts.synthesize("привет")

    assert "start_all.ps1" in str(e.value)


# --- Потоковая озвучка /say-stream (19.08.2026, найдено фаундером вживую:
# пауза перед голосовым ответом доходила до нескольких секунд, потому что
# /say ждала синтеза всего файла целиком) ---


def test_prepare_edge_stream_rejects_empty_text(monkeypatch):
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "edge")

    with pytest.raises(ValueError):
        tts.prepare_edge_stream("   ")


def test_prepare_edge_stream_requires_edge_engine(monkeypatch):
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "omnivoice")

    with pytest.raises(tts.VoiceUnavailable):
        tts.prepare_edge_stream("привет")


def test_prepare_edge_stream_off_by_default(monkeypatch):
    monkeypatch.delenv("NEXUS_TTS_ENGINE", raising=False)

    with pytest.raises(tts.VoiceUnavailable):
        tts.prepare_edge_stream("привет")


def test_prepare_edge_stream_clips_long_text(monkeypatch):
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "edge")
    monkeypatch.setenv("NEXUS_TTS_MAX_CHARS", "20")
    import edge_tts

    monkeypatch.setattr(edge_tts, "Communicate", _FakeCommunicate)

    communicate = tts.prepare_edge_stream("слово " * 20)

    assert len(communicate.text) <= 21
    assert communicate.text.endswith("…")


@pytest.mark.asyncio
async def test_stream_chunks_yields_only_audio_bytes():
    """WordBoundary и подобные служебные куски — не звук, их нельзя
    отправлять браузеру как есть, он попытается их проиграть."""
    communicate = _FakeCommunicate("текст", "voice")

    pieces = [c async for c in tts.stream_chunks(communicate)]

    assert pieces == [b"chunk1", b"chunk2"]


def test_say_stream_returns_400_for_empty_text(client, monkeypatch):
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "edge")

    r = client.get("/api/voice/say-stream", params={"text": "   "})

    assert r.status_code == 400


def test_say_stream_returns_503_when_voice_off(client, monkeypatch):
    monkeypatch.delenv("NEXUS_TTS_ENGINE", raising=False)

    r = client.get("/api/voice/say-stream", params={"text": "привет"})

    assert r.status_code == 503


def test_say_stream_returns_audio_bytes(client, monkeypatch):
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "edge")
    import edge_tts

    monkeypatch.setattr(edge_tts, "Communicate", _FakeCommunicate)

    r = client.get("/api/voice/say-stream", params={"text": "привет"})

    assert r.status_code == 200
    assert r.content == b"chunk1chunk2"
    assert r.headers["content-type"] == "audio/mpeg"


def test_say_stream_rejects_wrong_query_token(client, monkeypatch, temp_data_dir):
    from backend.core.jsonio import write_json

    write_json(temp_data_dir / "auth.json", {"token": "local-secret"})
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "edge")

    r = client.get("/api/voice/say-stream", params={"text": "привет", "token": "wrong"})

    assert r.status_code == 401


def test_say_stream_falls_back_to_whole_file_for_omnivoice(client, monkeypatch, tmp_path):
    """OmniVoice генерирует звук одним проходом — дробить на куски нечего,
    но тот же URL обязан всё равно отдать звук, не 503."""
    import httpx

    monkeypatch.setenv("NEXUS_TTS_ENGINE", "omnivoice")
    out = tmp_path / "voice_omnivoice_test.wav"
    out.write_bytes(b"RIFF....WAVEfake")

    async def fake_post(self, url, **kwargs):
        return httpx.Response(200, content=b"RIFF....WAVEfake", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    r = client.get("/api/voice/say-stream", params={"text": "привет"})

    assert r.status_code == 200
    assert r.content == b"RIFF....WAVEfake"
    assert r.headers["content-type"] == "audio/wav"


def test_say_stream_accepts_correct_query_token(client, monkeypatch, temp_data_dir):
    from backend.core.jsonio import write_json

    write_json(temp_data_dir / "auth.json", {"token": "local-secret"})
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "edge")
    import edge_tts

    monkeypatch.setattr(edge_tts, "Communicate", _FakeCommunicate)

    r = client.get(
        "/api/voice/say-stream", params={"text": "привет", "token": "local-secret"}
    )

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_omnivoice_synthesize_reports_server_error(monkeypatch):
    import httpx

    async def fake_post(self, url, **kwargs):
        return httpx.Response(500, json={"error": "модель упала"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "omnivoice")

    with pytest.raises(tts.VoiceUnavailable) as e:
        await tts.synthesize("привет")

    assert "модель упала" in str(e.value)
