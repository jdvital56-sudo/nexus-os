"""Тесты первого среза Content Factory: план -> озвучка -> approve/reject."""
import httpx
import pytest

from backend.core.config import settings as core_settings
from backend.core.errors import NotFoundError, ValidationError
from backend.services import content_factory as svc
from backend.models.schemas import ContentStatus


def _json_response(status: int, body: dict) -> httpx.Response:
    request = httpx.Request("GET", "https://fal.run/x")
    return httpx.Response(status, json=body, request=request)


def _bytes_response(status: int, content: bytes) -> httpx.Response:
    request = httpx.Request("GET", "https://fal.run/x")
    return httpx.Response(status, content=content, request=request)


class StubLLM:
    """Отвечает валидным JSON-планом, как настоящий LLMService в json_mode."""

    def __init__(self, raw: str | None = None):
        self.raw = raw or (
            '[{"script": "Сценарий один", "caption": "Подпись один", "hashtags": ["a"]},'
            ' {"script": "Сценарий два", "caption": "Подпись два", "hashtags": ["b"]}]'
        )
        self.calls: list[str] = []

    async def generate_response(self, user_message, context="", kind="interactive", json_mode=False):
        self.calls.append(user_message)
        return self.raw


@pytest.mark.asyncio
async def test_generate_plan_creates_drafts():
    items = await svc.generate_plan("утренние ритуалы", count=2, llm=StubLLM())

    assert len(items) == 2
    assert items[0].topic == "утренние ритуалы"
    assert items[0].script == "Сценарий один"
    assert items[0].status == ContentStatus.DRAFT
    assert items[0].voice_file is None

    stored = svc.list_items()
    assert len(stored) == 2


@pytest.mark.asyncio
async def test_generate_plan_wraps_items_object():
    raw = '{"items": [{"script": "S", "caption": "C", "hashtags": []}]}'
    items = await svc.generate_plan("тема", count=1, llm=StubLLM(raw))
    assert len(items) == 1


@pytest.mark.asyncio
async def test_generate_plan_rejects_non_json():
    with pytest.raises(ValidationError):
        await svc.generate_plan("тема", count=1, llm=StubLLM("это не json"))


@pytest.mark.asyncio
async def test_generate_plan_rejects_empty_topic():
    with pytest.raises(ValidationError):
        await svc.generate_plan("   ", count=1, llm=StubLLM())


@pytest.mark.asyncio
async def test_generate_plan_caps_count_and_platforms():
    items = await svc.generate_plan("тема", count=1, platforms=["youtube"], llm=StubLLM())
    assert items[0].platforms == ["youtube"]


def test_get_item_missing_raises():
    with pytest.raises(NotFoundError):
        svc.get_item("нет такого")


@pytest.mark.asyncio
async def test_synthesize_voice_moves_file_and_updates_item(tmp_path, monkeypatch):
    [item] = await svc.generate_plan("тема", count=1, llm=StubLLM())

    fake_audio = tmp_path / "raw.mp3"
    fake_audio.write_bytes(b"fake-audio-bytes")

    async def fake_synthesize(text, voice=None):
        return fake_audio

    monkeypatch.setattr("backend.services.tts.synthesize", fake_synthesize)

    updated = await svc.synthesize_voice(item.id)

    assert updated.voice_file is not None
    assert updated.status == ContentStatus.DRAFT
    path = svc.voice_file_path(item.id)
    assert path.is_file()
    assert path.read_bytes() == b"fake-audio-bytes"


@pytest.mark.asyncio
async def test_synthesize_voice_missing_script_raises():
    items = await svc.generate_plan("тема", count=1, llm=StubLLM(
        '[{"script": "", "caption": "C", "hashtags": []}]'
    ))
    with pytest.raises(ValidationError):
        await svc.synthesize_voice(items[0].id)


@pytest.mark.asyncio
async def test_voice_not_ready_raises():
    [item] = await svc.generate_plan("тема", count=1, llm=StubLLM())
    with pytest.raises(ValidationError):
        svc.voice_file_path(item.id)


@pytest.mark.asyncio
async def test_generate_image_missing_key_raises(monkeypatch):
    [item] = await svc.generate_plan("тема", count=1, llm=StubLLM())
    monkeypatch.setattr(core_settings, "fal_api_key", "")
    with pytest.raises(ValidationError):
        await svc.generate_image(item.id)


@pytest.mark.asyncio
async def test_generate_image_downloads_and_updates_item(monkeypatch):
    [item] = await svc.generate_plan("тема", count=1, llm=StubLLM())
    monkeypatch.setattr(core_settings, "fal_api_key", "test-key")

    async def fake_post(self, url, **kwargs):
        assert url == f"https://fal.run/{svc.FAL_IMAGE_MODEL}"
        assert kwargs["headers"]["Authorization"] == "Key test-key"
        return _json_response(200, {"images": [{"url": "https://fal.media/x.jpg"}]})

    async def fake_get(self, url, **kwargs):
        assert url == "https://fal.media/x.jpg"
        return _bytes_response(200, b"fake-image-bytes")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    updated = await svc.generate_image(item.id)

    assert updated.image_file is not None
    path = svc.image_file_path(item.id)
    assert path.read_bytes() == b"fake-image-bytes"


@pytest.mark.asyncio
async def test_image_not_ready_raises():
    [item] = await svc.generate_plan("тема", count=1, llm=StubLLM())
    with pytest.raises(ValidationError):
        svc.image_file_path(item.id)


@pytest.mark.asyncio
async def test_generate_video_polls_queue_and_downloads(monkeypatch):
    [item] = await svc.generate_plan("тема", count=1, llm=StubLLM())
    monkeypatch.setattr(core_settings, "fal_api_key", "test-key")

    async def fake_post(self, url, **kwargs):
        assert url == f"https://queue.fal.run/{svc.FAL_VIDEO_MODEL}"
        return _json_response(200, {
            "request_id": "r1",
            "status_url": "https://queue.fal.run/x/requests/r1/status",
            "response_url": "https://queue.fal.run/x/requests/r1",
        })

    async def fake_get(self, url, **kwargs):
        if url.endswith("/status"):
            return _json_response(200, {"status": "COMPLETED"})
        if url.endswith("/requests/r1"):
            return _json_response(200, {"video": {"url": "https://fal.media/x.mp4"}})
        assert url == "https://fal.media/x.mp4"
        return _bytes_response(200, b"fake-video-bytes")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    updated = await svc.generate_video(item.id)

    assert updated.video_file is not None
    path = svc.video_file_path(item.id)
    assert path.read_bytes() == b"fake-video-bytes"


@pytest.mark.asyncio
async def test_generate_video_error_status_raises(monkeypatch):
    [item] = await svc.generate_plan("тема", count=1, llm=StubLLM())
    monkeypatch.setattr(core_settings, "fal_api_key", "test-key")

    async def fake_post(self, url, **kwargs):
        return _json_response(200, {
            "request_id": "r1",
            "status_url": "https://queue.fal.run/x/requests/r1/status",
            "response_url": "https://queue.fal.run/x/requests/r1",
        })

    async def fake_get(self, url, **kwargs):
        return _json_response(200, {"status": "ERROR"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(ValidationError):
        await svc.generate_video(item.id)


@pytest.mark.asyncio
async def test_video_not_ready_raises():
    [item] = await svc.generate_plan("тема", count=1, llm=StubLLM())
    with pytest.raises(ValidationError):
        svc.video_file_path(item.id)


@pytest.mark.asyncio
async def test_approve_and_reject_change_status():
    [item] = await svc.generate_plan("тема", count=1, llm=StubLLM())

    approved = svc.set_status(item.id, ContentStatus.APPROVED)
    assert approved.status == ContentStatus.APPROVED

    rejected = svc.set_status(item.id, ContentStatus.REJECTED)
    assert rejected.status == ContentStatus.REJECTED


@pytest.mark.asyncio
async def test_list_items_filters_by_status():
    [a] = await svc.generate_plan("тема1", count=1, llm=StubLLM())
    [b] = await svc.generate_plan("тема2", count=1, llm=StubLLM())
    svc.set_status(a.id, ContentStatus.APPROVED)

    approved_only = svc.list_items(status="approved")
    assert len(approved_only) == 1
    assert approved_only[0].id == a.id


@pytest.mark.asyncio
async def test_delete_item_removes_entry_and_voice_file(monkeypatch, tmp_path):
    [item] = await svc.generate_plan("тема", count=1, llm=StubLLM())

    fake_audio = tmp_path / "raw.mp3"
    fake_audio.write_bytes(b"bytes")

    async def fake_synthesize(text, voice=None):
        return fake_audio

    monkeypatch.setattr("backend.services.tts.synthesize", fake_synthesize)
    await svc.synthesize_voice(item.id)
    voice_path = svc.voice_file_path(item.id)
    assert voice_path.is_file()

    svc.delete_item(item.id)

    assert not voice_path.is_file()
    with pytest.raises(NotFoundError):
        svc.get_item(item.id)


def test_delete_missing_item_raises():
    with pytest.raises(NotFoundError):
        svc.delete_item("нет такого")


@pytest.mark.asyncio
async def test_delete_item_removes_image_and_video_files(monkeypatch):
    [item] = await svc.generate_plan("тема", count=1, llm=StubLLM())
    monkeypatch.setattr(core_settings, "fal_api_key", "test-key")

    async def fake_post(self, url, **kwargs):
        if "queue.fal.run" in url:
            return _json_response(200, {
                "request_id": "r1",
                "status_url": "https://queue.fal.run/x/requests/r1/status",
                "response_url": "https://queue.fal.run/x/requests/r1",
            })
        return _json_response(200, {"images": [{"url": "https://fal.media/x.jpg"}]})

    async def fake_get(self, url, **kwargs):
        if url.endswith("/status"):
            return _json_response(200, {"status": "COMPLETED"})
        if url.endswith("/requests/r1"):
            return _json_response(200, {"video": {"url": "https://fal.media/x.mp4"}})
        return _bytes_response(200, b"bytes")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    await svc.generate_image(item.id)
    await svc.generate_video(item.id)
    image_path = svc.image_file_path(item.id)
    video_path = svc.video_file_path(item.id)

    svc.delete_item(item.id)

    assert not image_path.is_file()
    assert not video_path.is_file()


# --- API ---


def test_api_create_plan(client, monkeypatch):
    class FakeLLMService:
        def __init__(self, *args, **kwargs):
            pass

        async def generate_response(self, user_message, context="", kind="interactive", json_mode=False):
            return '[{"script": "S", "caption": "C", "hashtags": ["x"]}]'

    import backend.services.llm as llm_mod
    monkeypatch.setattr(llm_mod, "LLMService", FakeLLMService)

    r = client.post("/api/content/plan", json={"topic": "новости", "count": 1})
    assert r.status_code == 201
    data = r.json()
    assert len(data) == 1
    assert data[0]["topic"] == "новости"
    assert data[0]["status"] == "draft"


def test_api_generate_image(client, monkeypatch):
    class FakeLLMService:
        def __init__(self, *args, **kwargs):
            pass

        async def generate_response(self, user_message, context="", kind="interactive", json_mode=False):
            return '[{"script": "S", "caption": "C", "hashtags": []}]'

    import backend.services.llm as llm_mod
    monkeypatch.setattr(llm_mod, "LLMService", FakeLLMService)
    monkeypatch.setattr(core_settings, "fal_api_key", "test-key")

    async def fake_post(self, url, **kwargs):
        return _json_response(200, {"images": [{"url": "https://fal.media/x.jpg"}]})

    async def fake_get(self, url, **kwargs):
        return _bytes_response(200, b"fake-image-bytes")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    r = client.post("/api/content/plan", json={"topic": "тема", "count": 1})
    item_id = r.json()[0]["id"]

    r = client.post(f"/api/content/{item_id}/image")
    assert r.status_code == 200
    assert r.json()["image_file"] is not None

    r = client.get(f"/api/content/{item_id}/image")
    assert r.status_code == 200
    assert r.content == b"fake-image-bytes"


def test_api_approve_reject_flow(client, monkeypatch):
    class FakeLLMService:
        def __init__(self, *args, **kwargs):
            pass

        async def generate_response(self, user_message, context="", kind="interactive", json_mode=False):
            return '[{"script": "S", "caption": "C", "hashtags": []}]'

    import backend.services.llm as llm_mod
    monkeypatch.setattr(llm_mod, "LLMService", FakeLLMService)

    r = client.post("/api/content/plan", json={"topic": "тема", "count": 1})
    item_id = r.json()[0]["id"]

    r = client.post(f"/api/content/{item_id}/approve")
    assert r.json()["status"] == "approved"

    r = client.get("/api/content?status=approved")
    assert len(r.json()) == 1

    r = client.delete(f"/api/content/{item_id}")
    assert r.json() == {"ok": True}

    r = client.get(f"/api/content/{item_id}")
    assert r.status_code == 404


# --- Отдача медиа для <img>/<audio> (23.08.2026) ---


def test_media_is_served_to_img_tag_without_auth_header(client, monkeypatch):
    """Найдено живым прогоном: карточка показывала <img src> на этот URL,
    но тег не умеет слать Authorization — браузер получал 401 и на экране
    была пустота вместо реально сгенерированной картинки. Токен из строки
    запроса, тот же приём, что у /api/voice/say-stream."""
    import backend.api.content_factory as api_mod

    class FakeLLMService:
        def __init__(self, *args, **kwargs):
            pass

        async def generate_response(self, user_message, context="", kind="interactive", json_mode=False):
            return '[{"script": "S", "caption": "C", "hashtags": []}]'

    import backend.services.llm as llm_mod
    monkeypatch.setattr(llm_mod, "LLMService", FakeLLMService)
    monkeypatch.setattr(core_settings, "fal_api_key", "test-key")

    async def fake_post(self, url, **kwargs):
        return _json_response(200, {"images": [{"url": "https://fal.media/x.jpg"}]})

    async def fake_get(self, url, **kwargs):
        return _bytes_response(200, b"fake-image-bytes")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    item_id = client.post("/api/content/plan", json={"topic": "тема", "count": 1}).json()[0]["id"]
    client.post(f"/api/content/{item_id}/image")

    # Токен в приложении включён — без него отдавать нельзя
    monkeypatch.setattr(api_mod, "_load_token", lambda: "секрет")
    assert client.get(f"/api/content/{item_id}/image").status_code == 401
    assert client.get(f"/api/content/{item_id}/image?token=неверный").status_code == 401

    ok = client.get(f"/api/content/{item_id}/image?token=секрет")
    assert ok.status_code == 200
    assert ok.content == b"fake-image-bytes"


def test_media_is_open_when_no_token_is_configured(client, monkeypatch):
    """Токен не настроен вообще — локальная установка без пароля, как и
    остальные ручки в этом случае."""
    import backend.api.content_factory as api_mod

    monkeypatch.setattr(api_mod, "_load_token", lambda: None)
    # Файла нет — важен только код ответа авторизации, не 401
    assert client.get("/api/content/нет-такого/image").status_code != 401
