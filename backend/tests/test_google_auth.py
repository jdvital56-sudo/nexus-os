"""Единый вход в Google для почты и календаря.

Раньше почта искала credentials.json в корне проекта, а календарь —
google_credentials.json в папке данных: один и тот же файл пришлось бы
класть дважды и входить два раза.
"""
import pytest

from backend.services import google_auth


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(google_auth, "CREDENTIALS_PATHS", (tmp_path / "google_credentials.json",))
    monkeypatch.setattr(google_auth, "TOKEN_FILE", tmp_path / "google_token.json")
    return tmp_path


def test_without_file_says_where_to_put_it():
    state = google_auth.status()

    assert state["ready"] is False
    assert "google_credentials.json" in state["detail"]


def test_with_file_but_no_login_says_what_to_run(isolate):
    (isolate / "google_credentials.json").write_text("{}", encoding="utf-8")

    state = google_auth.status()

    assert state["ready"] is False
    assert "google-auth" in state["detail"]


def test_ready_when_token_exists(isolate):
    (isolate / "google_credentials.json").write_text("{}", encoding="utf-8")
    (isolate / "google_token.json").write_text("{}", encoding="utf-8")

    assert google_auth.status()["ready"] is True


def test_mail_and_calendar_share_the_same_login(isolate):
    """Оба сервиса смотрят в одно место — файл кладётся один раз."""
    from backend.services import calendar as calendar_svc
    from backend.services.gmail import gmail_client

    assert calendar_svc.is_configured() is False
    assert gmail_client.is_configured() is False

    (isolate / "google_credentials.json").write_text("{}", encoding="utf-8")

    assert calendar_svc.is_configured() is True
    assert gmail_client.is_configured() is True


def test_authorize_without_file_explains_why(isolate):
    with pytest.raises(google_auth.GoogleNotConnected) as e:
        google_auth.authorize()

    assert "Google Cloud Console" in str(e.value)


def test_scopes_do_not_allow_sending_mail():
    """Отправки писем нет и в правах: система физически не сможет отправить."""
    assert not any("gmail.send" in scope for scope in google_auth.SCOPES)
    assert any("gmail.compose" in scope for scope in google_auth.SCOPES)
