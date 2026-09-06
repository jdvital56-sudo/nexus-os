"""SSRF: соединение обязано идти на тот адрес, который проверили.

Находка аудита 07.09.2026. `_check_public_host` резолвил имя и отдавал его
обратно, а httpx резолвил это имя ВТОРОЙ раз при установке соединения.
Между двумя резолвами щель: домен с TTL=0 отвечает публичным адресом на
проверку и `127.0.0.1` на соединение. Проверка проходит честно, запрос
уходит во внутреннюю сеть.

Дыра была воспроизведена на живом стенде до правки: проверка сказала
«публичный», запрос пришёл на локальный сервер, содержимое вернулось
агенту. Тесты ниже закрепляют оба конца — и что чужое не пройдёт, и что
обычный сайт по-прежнему открывается. Второе не менее важно: защита,
которая ломает нормальную работу, будет отключена первой же правкой.
"""
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from crew import tools


@pytest.fixture
def local_server():
    """Настоящий HTTP-сервер на localhost — роль «внутренней сети»."""
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append({"path": self.path, "host": self.headers.get("Host")})
            body = "<html>СЕКРЕТ ВНУТРЕННЕЙ СЕТИ</html>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1], hits
    server.shutdown()


class Ctx:
    async def ask(self, *a, **k):
        return True


# === Проверка адреса =======================================================


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8420/api/wallet",
        "http://localhost:8420/api/wallet",
        "http://169.254.169.254/latest/meta-data/",  # метаданные облака
        "http://10.0.0.5/",
        "http://192.168.1.1/",
    ],
)
def test_internal_addresses_are_refused(url):
    with pytest.raises(ValueError):
        tools._resolve_public_address(url)


def test_public_address_is_allowed_and_pinned():
    """Обратная сторона: обычный сайт открывается, и мы получаем на руки
    конкретный адрес, а не только имя."""
    host, ip = tools._resolve_public_address("https://example.com/about")
    assert host == "example.com"
    assert ip and ip[0].isdigit() or ":" in ip, "должен вернуться разрешённый адрес"


def test_non_http_schemes_are_refused():
    for url in ("file:///C:/Users/x/.env", "ftp://example.com/x", "gopher://x/"):
        with pytest.raises(ValueError):
            tools._resolve_public_address(url)


# === Закрепление адреса: суть правки =======================================


@pytest.mark.asyncio
async def test_connection_goes_to_the_checked_address_not_a_new_lookup(
    local_server, monkeypatch
):
    """Главный тест. Проверка «одобрила» публичный адрес — значит туда и
    соединяемся, что бы имя ни резолвило во второй раз.

    203.0.113.1 — из TEST-NET-3, он никуда не ведёт. Правильный исход:
    соединение не установилось. Неправильный: стук в локальный сервер.
    """
    port, hits = local_server
    monkeypatch.setattr(
        tools, "_resolve_public_address", lambda url: ("attacker.example", "203.0.113.1")
    )

    result = await tools._fetch_url(Ctx(), {"url": f"http://localhost:{port}/secret"})

    assert hits == [], "запрос ушёл во внутреннюю сеть — закрепление не работает"
    assert "СЕКРЕТ" not in result


@pytest.mark.asyncio
async def test_normal_fetch_still_works_and_keeps_the_real_host(local_server, monkeypatch):
    """Обратная сторона закрепления: страница по-прежнему читается, а сайт
    получает НАСТОЯЩЕЕ имя в заголовке Host. Без этого виртуальные хосты
    (а это почти весь интернет) отдавали бы не тот сайт или 404."""
    port, hits = local_server
    monkeypatch.setattr(
        tools, "_resolve_public_address", lambda url: ("klient.example", "127.0.0.1")
    )

    result = await tools._fetch_url(Ctx(), {"url": f"http://klient.example:{port}/about"})

    assert len(hits) == 1, "обычный запрос обязан дойти"
    assert hits[0]["path"] == "/about"
    assert hits[0]["host"] == f"klient.example:{port}", "сайт должен видеть имя, а не цифры"
    assert "СЕКРЕТ" in result


@pytest.mark.asyncio
async def test_relative_redirect_keeps_the_hostname(local_server, monkeypatch):
    """Относительный Location считается от логического адреса, а не от того,
    где подставлен IP. Иначе на втором витке имя терялось бы, и сайт получил
    бы в Host цифры."""
    port, hits = local_server

    class Redirecting(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append({"path": self.path, "host": self.headers.get("Host")})
            if self.path == "/start":
                self.send_response(302)
                self.send_header("Location", "/finish")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = "<html>дошли</html>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Redirecting)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    hits.clear()

    monkeypatch.setattr(
        tools, "_resolve_public_address", lambda url: ("klient.example", "127.0.0.1")
    )
    result = await tools._fetch_url(Ctx(), {"url": f"http://klient.example:{port}/start"})
    server.shutdown()

    assert [h["path"] for h in hits] == ["/start", "/finish"]
    assert all(h["host"] == f"klient.example:{port}" for h in hits), "имя потерялось на редиректе"
    assert "дошли" in result


@pytest.mark.asyncio
async def test_redirect_target_is_checked_too(local_server, monkeypatch):
    """Уже работало до правки, но обязано работать и после: увести на
    внутренний адрес ответом 302 нельзя."""
    port, hits = local_server
    seen = []

    def check(url):
        seen.append(url)
        if "localhost" in url or "127.0.0.1" in url:
            raise ValueError("внутренняя сеть")
        return ("sait.example", "127.0.0.1")

    class Redirecting(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append({"path": self.path, "host": self.headers.get("Host")})
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{port}/api/wallet")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Redirecting)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    redirect_port = server.server_address[1]
    hits.clear()

    monkeypatch.setattr(tools, "_resolve_public_address", check)
    result = await tools._fetch_url(
        Ctx(), {"url": f"http://sait.example:{redirect_port}/go"}
    )
    server.shutdown()

    assert "отклонён" in result.lower()
    assert any("127.0.0.1" in u for u in seen), "адрес после редиректа должен проверяться"
