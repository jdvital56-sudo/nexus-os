"""Общий сервис голоса (voice_engine/piper_server.py).

Синтез здесь не гоняется: он стоит секунду процессорного времени и требует
модель на 60 МБ. Тесты стерегут то, что ломалось на практике, — где сервис
ищет голоса и что он отвечает, когда голоса нет. Живая проверка (реальный
WAV, речь из колонок, замеры) делалась отдельно 25.08.2026.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Сервис лежит вне пакета backend — он и не должен от него зависеть,
# в этом весь смысл общего сервиса.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "voice_engine"))

piper_server = pytest.importorskip("piper_server")


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Сервис без прогрева: прогрев грузит настоящую модель."""
    monkeypatch.setattr(piper_server, "VOICES_DIR", tmp_path)
    monkeypatch.setattr(piper_server, "warm_up", lambda: None)
    piper_server._voices.clear()
    with TestClient(piper_server.app) as c:
        yield c


def test_health_is_honest_about_being_empty(client):
    """Пустой ответ обязан отличаться от рабочего: «ready: true» без единого
    голоса означал бы обещание звука, которого не будет."""
    body = client.get("/health").json()
    assert body["ready"] is False
    assert body["voices"] == []


def test_missing_voice_is_404_with_the_list(client, tmp_path):
    (tmp_path / "ru_RU-dmitri-medium.onnx").write_bytes(b"not a real model")
    response = client.post("/say", json={"text": "привет", "voice": "нет-такого"})
    assert response.status_code == 404
    # Просто «не найдено» заставит гадать, что вообще есть
    assert "ru_RU-dmitri-medium" in response.json()["detail"]


def test_empty_text_is_rejected(client):
    assert client.post("/say", json={"text": "   "}).status_code == 400
    assert client.post("/speak", json={"text": ""}).status_code == 400


def test_only_downloaded_voices_are_listed(client, tmp_path):
    """Показать голос, которого нет на диске, значит отдать 404 тому, кто
    его выберет из списка."""
    (tmp_path / "ru_RU-irina-medium.onnx").write_bytes(b"x")
    (tmp_path / "ru_RU-irina-medium.onnx.json").write_text("{}")
    (tmp_path / "README.md").write_text("не голос")
    assert client.get("/voices").json()["voices"] == ["ru_RU-irina-medium"]


def test_shared_folder_wins_over_the_project_one(monkeypatch, tmp_path):
    """Голоса — машинные данные: рабочих деревьев бывает три, и сервис не
    должен зависеть от того, из какого его запустили (25.08.2026)."""
    shared = tmp_path / ".nexsys" / "piper_voices"
    shared.mkdir(parents=True)
    (shared / "ru_RU-dmitri-medium.onnx").write_bytes(b"x")

    monkeypatch.delenv("PIPER_VOICES_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert piper_server._voices_dir() == shared


def test_project_folder_is_the_fallback(monkeypatch, tmp_path):
    """Обновление не должно лишить голоса установку, где переезд ещё не
    случился."""
    monkeypatch.delenv("PIPER_VOICES_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert piper_server._voices_dir().name == "piper_voices"
    assert ".nexsys" not in str(piper_server._voices_dir())


def test_explicit_path_wins_over_everything(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPER_VOICES_DIR", str(tmp_path / "своё место"))
    assert piper_server._voices_dir() == tmp_path / "своё место"
