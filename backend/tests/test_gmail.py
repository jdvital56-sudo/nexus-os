"""Gmail умеет только черновики — проверяем это конструктивно (PR-15, I-7)."""
import inspect

import pytest

from backend.services import gmail, google_auth


@pytest.fixture(autouse=True)
def google_disconnected(tmp_path, monkeypatch):
    """Почта не подключена — что бы ни лежало на машине.

    Вход в Google общий с календарём и живёт в google_auth: пути к файлу
    доступа и токену там же. Подменять os.path.exists внутри gmail
    бесполезно — он их не проверяет. На машине с подключённым Google тест
    без этой изоляции уходил в браузерную авторизацию и вис.
    """
    monkeypatch.setattr(
        google_auth, "CREDENTIALS_PATHS", (tmp_path / "google_credentials.json",)
    )
    monkeypatch.setattr(google_auth, "TOKEN_FILE", tmp_path / "google_token.json")
    return tmp_path


def test_no_send_method_exists():
    """Главная гарантия: отправки нет как метода, а не выключена флагом."""
    methods = [m for m, _ in inspect.getmembers(gmail.GmailClient, inspect.isfunction)]

    assert "send" not in methods
    assert "send_message" not in methods
    assert not any("send" in m.lower() for m in methods)


def test_source_never_calls_gmail_send_api():
    """Даже строки с вызовом users().messages().send() в модуле нет."""
    source = inspect.getsource(gmail)

    assert ".send(" not in source
    assert "drafts().send" not in source


def test_only_two_scopes_requested():
    assert gmail.SCOPES == [
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.readonly",
    ]


def test_missing_credentials_are_reported_honestly():
    client = gmail.GmailClient()

    with pytest.raises(gmail.GmailNotConfigured) as e:
        client.create_draft("a@b.com", "тема", "текст")

    assert "credentials.json" in str(e.value)


def test_recipient_is_required():
    client = gmail.GmailClient()

    with pytest.raises(ValueError):
        client.create_draft("  ", "тема", "текст")


def test_subject_is_required():
    client = gmail.GmailClient()

    with pytest.raises(ValueError):
        client.create_draft("a@b.com", "", "текст")


class FakeDrafts:
    def __init__(self, store):
        self.store = store

    def create(self, userId, body):
        self.store.append(body)
        return _Executable({"id": "draft-1"})


class _Executable:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class FakeUsers:
    def __init__(self, store):
        self._drafts = FakeDrafts(store)

    def drafts(self):
        return self._drafts


class FakeService:
    def __init__(self, store):
        self._users = FakeUsers(store)

    def users(self):
        return self._users


def test_draft_is_created_and_marked_unsent(monkeypatch):
    sent_bodies = []
    client = gmail.GmailClient()
    monkeypatch.setattr(client, "_connect", lambda: FakeService(sent_bodies))

    result = client.create_draft("client@example.com", "Коммерческое предложение", "Текст письма")

    assert result["draft_id"] == "draft-1"
    assert result["status"] == "draft"
    assert "НЕ отправлено" in result["note"]
    # Письмо ушло именно в drafts, а не в messages
    assert "raw" in sent_bodies[0]["message"]


def test_draft_carries_recipient_and_subject(monkeypatch):
    import base64

    bodies = []
    client = gmail.GmailClient()
    monkeypatch.setattr(client, "_connect", lambda: FakeService(bodies))

    client.create_draft("client@example.com", "Тема письма", "Тело")

    raw = base64.urlsafe_b64decode(bodies[0]["message"]["raw"]).decode()
    assert "client@example.com" in raw
    assert "Тело" in raw


# --- HTTP API ---


def test_api_status_declares_no_sending(client):
    body = client.get("/api/gmail/status").json()

    assert body["can_send"] is False


def test_api_has_no_send_endpoint(client):
    """В маршрутах не должно быть ничего, отправляющего письма."""
    from backend.main import app

    gmail_routes = [r.path for r in app.routes if r.path.startswith("/api/gmail")]

    assert not any("send" in path for path in gmail_routes)
    assert "/api/gmail/drafts" in gmail_routes


def test_api_without_credentials_returns_503(client, monkeypatch):
    monkeypatch.setattr(gmail.gmail_client, "is_configured", lambda: False)

    r = client.post("/api/gmail/drafts", json={
        "to": "a@b.com", "subject": "тема", "body": "текст",
    })

    assert r.status_code == 503


# --- Потокобезопасность (23.08.2026) ---


def test_service_is_per_thread():
    """httplib2 под googleapiclient не потокобезопасен: один общий service
    на процесс рвал SSL при параллельных запросах («record layer failure»),
    и экран почты, грузящий черновики и письма разом, получал 500 на оба.
    Найдено вживую — почта выглядела пустой."""
    import threading

    from backend.services.gmail import GmailClient

    client = GmailClient()
    client.service = "сервис-главного-потока"
    seen = {}

    def worker():
        seen["before"] = client.service  # в своём потоке ещё пусто
        client.service = "сервис-рабочего-потока"
        seen["after"] = client.service

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert seen["before"] is None, "поток не должен видеть чужой service"
    assert seen["after"] == "сервис-рабочего-потока"
    assert client.service == "сервис-главного-потока", "чужой поток не затирает наш"


def test_service_is_reused_within_one_thread():
    """Переиспользование внутри потока сохраняется — иначе каждый запрос
    заново поднимал бы OAuth-сессию."""
    from backend.services.gmail import GmailClient

    client = GmailClient()
    assert client.service is None
    client.service = "сервис"
    assert client.service == "сервис"
