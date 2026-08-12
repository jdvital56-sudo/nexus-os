"""Smoke test — API health endpoint."""


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["service"] == "nexus-os"


# --- Ошибки должны быть видны фронтенду (найдено 2026-08-12) ---


def test_missing_resource_is_404_not_500(client):
    """Своя NotFoundError вместо встроенной FileNotFoundError: раньше
    «факта нет» приезжало как 500 INTERNAL — сбой сервера вместо ответа."""
    r = client.get("/api/memory/facts/нет-такого")

    assert r.status_code == 404
    assert r.json()["code"] == "NOT_FOUND"


def test_server_error_keeps_cors_headers(monkeypatch):
    """Ответ 500 без CORS-заголовков браузер прячет целиком, и фронтенд
    показывает «нет связи» вместо настоящей причины."""
    from fastapi.testclient import TestClient

    import backend.core.config as cfg
    import backend.core.errors as errors_mod
    import backend.services.memory as mem_svc
    from backend.main import app

    monkeypatch.setattr(cfg, "CORS_ORIGINS", ["http://localhost:5173"])

    def boom(*args, **kwargs):
        raise RuntimeError("внутренняя поломка")

    monkeypatch.setattr(mem_svc, "get_stats", boom)
    # Исключение должно дойти до обработчика, а не всплыть в тест
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/memory/stats", headers={"Origin": "http://localhost:5173"})

    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "внутренняя поломка" in r.json()["error"]
