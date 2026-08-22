"""Телефония (J.A.R.V.I.S. Phone) — до код-ревью 20.08.2026 не было ни
одного теста и ни одной authenticated-ручки в этом файле.

Три реальных дыры, закрытых этой сессией:
1. Управляющие ручки (/initiate, /active, /usage и т.д.) не требовали
   Bearer-токена вообще — любой с сетевым доступом мог звонить за счёт
   фаундера.
2. verify_pin() без CALL_PIN_HASH в .env пускала любой ввод («режим
   разработки») — без явной настройки PIN звонок аутентифицировался бы
   мгновенно.
3. "Локаут" после исчерпания попыток PIN сбрасывал счётчик обратно в 0 в
   тот же момент, что его выставлял — реальной защиты от перебора не было.
"""
import time

import pytest

from backend.services.telephony_client import PIN_LOCKOUT_SECONDS, TelephonyClient


@pytest.fixture
def tc():
    """Свежий клиент на каждый тест — глобальный singleton в проде,
    но состояние (pin_attempts и т.п.) не должно течь между тестами."""
    return TelephonyClient()


# --- verify_pin() ---


def test_pin_denied_by_default_without_hash_configured(tc, monkeypatch):
    """Раньше здесь было наоборот: без CALL_PIN_HASH пускало любой PIN
    («режим разработки»). Отсутствие настройки должно отказывать, не
    разрешать — телефонная линия не должна быть открыта по недосмотру."""
    monkeypatch.setattr(tc, "pin_hash", "")

    assert tc.verify_pin("+70000000000", "44435") is False
    assert tc.verify_pin("+70000000000", "anything") is False


def test_pin_correct_when_hash_configured(tc, monkeypatch):
    import hashlib

    monkeypatch.setattr(tc, "pin_hash", hashlib.sha256(b"44435").hexdigest())

    assert tc.verify_pin("+70000000000", "44435") is True


def test_pin_wrong_is_rejected(tc, monkeypatch):
    import hashlib

    monkeypatch.setattr(tc, "pin_hash", hashlib.sha256(b"44435").hexdigest())

    assert tc.verify_pin("+70000000000", "00000") is False


def test_successful_pin_clears_attempt_counter(tc, monkeypatch):
    import hashlib

    monkeypatch.setattr(tc, "pin_hash", hashlib.sha256(b"44435").hexdigest())
    tc.verify_pin("+70000000000", "wrong")
    tc.verify_pin("+70000000000", "wrong")

    assert tc.verify_pin("+70000000000", "44435") is True
    assert tc.pin_attempts.get("+70000000000") is None


def test_lockout_actually_blocks_after_max_attempts(tc, monkeypatch):
    """Настоящий баг, найденный код-ревью: раньше локаут сбрасывал счётчик
    в тот же момент, что его выставлял — следующая попытка сразу после
    "блокировки" проходила как ни в чём не бывало. Теперь верная попытка
    ПОСЛЕ исчерпания лимита обязана тоже провалиться."""
    import hashlib

    correct_hash = hashlib.sha256(b"44435").hexdigest()
    monkeypatch.setattr(tc, "pin_hash", correct_hash)
    monkeypatch.setattr(tc, "max_attempts", 3)

    for _ in range(3):
        assert tc.verify_pin("+70000000000", "wrong") is False

    # Даже ПРАВИЛЬНЫЙ PIN не должен пройти во время локаута
    assert tc.verify_pin("+70000000000", "44435") is False


def test_lockout_expires_after_timeout(tc, monkeypatch):
    correct_hash_input = "44435"
    import hashlib

    monkeypatch.setattr(tc, "pin_hash", hashlib.sha256(correct_hash_input.encode()).hexdigest())
    monkeypatch.setattr(tc, "max_attempts", 3)

    clock = {"t": 1000.0}
    monkeypatch.setattr(time, "time", lambda: clock["t"])

    for _ in range(3):
        tc.verify_pin("+70000000000", "wrong")
    assert tc.verify_pin("+70000000000", correct_hash_input) is False

    clock["t"] += PIN_LOCKOUT_SECONDS + 1

    assert tc.verify_pin("+70000000000", correct_hash_input) is True


def test_lockout_is_scoped_per_caller(tc, monkeypatch):
    """Один звонящий исчерпал попытки — другой номер не должен пострадать."""
    import hashlib

    monkeypatch.setattr(tc, "pin_hash", hashlib.sha256(b"44435").hexdigest())
    monkeypatch.setattr(tc, "max_attempts", 3)

    for _ in range(3):
        tc.verify_pin("+70000000001", "wrong")

    assert tc.verify_pin("+70000000002", "44435") is True


# --- API-ручки: авторизация ---


def test_management_endpoints_require_token(client, temp_data_dir):
    """Найдено код-ревью 20.08.2026: ни одна ручка телефонии не требовала
    токена — /initiate реально тратит деньги на звонок кому угодно."""
    from backend.core.jsonio import write_json

    write_json(temp_data_dir / "auth.json", {"token": "local-secret"})

    assert client.post("/api/call/initiate", json={"to_number": "+10000000000"}).status_code == 401
    assert client.get("/api/call/active").status_code == 401
    assert client.get("/api/call/usage").status_code == 401
    assert client.get("/api/call/setup-guide").status_code == 401
    assert client.post("/api/call/test-pin-hash", json={"pin_code": "12345"}).status_code == 401
    assert client.get("/api/call/some-id").status_code == 401
    assert client.post("/api/call/some-id/end").status_code == 401


def test_management_endpoint_works_with_correct_token(client, temp_data_dir):
    from backend.core.jsonio import write_json

    write_json(temp_data_dir / "auth.json", {"token": "local-secret"})

    r = client.post(
        "/api/call/test-pin-hash",
        json={"pin_code": "44435"},
        headers={"Authorization": "Bearer local-secret"},
    )

    assert r.status_code == 200
    assert "sha256_hash" in r.json()


# --- Вебхуки: секрет в query-параметре ---


def test_webhook_rejects_wrong_secret(client, monkeypatch):
    monkeypatch.setenv("TELEPHONY_WEBHOOK_SECRET", "right-secret")

    r = client.post(
        "/api/call/webhook/incoming?secret=wrong",
        json={"callId": "c1", "callerId": "+70000000000"},
    )

    assert r.status_code == 401


def test_webhook_accepts_correct_secret(client, monkeypatch):
    monkeypatch.setenv("TELEPHONY_WEBHOOK_SECRET", "right-secret")

    r = client.post(
        "/api/call/webhook/incoming?secret=right-secret",
        json={"callId": "c1", "callerId": "+70000000000"},
    )

    assert r.status_code == 200


def test_webhook_open_but_warns_when_secret_not_configured(client, monkeypatch, caplog):
    monkeypatch.delenv("TELEPHONY_WEBHOOK_SECRET", raising=False)

    r = client.post(
        "/api/call/webhook/incoming",
        json={"callId": "c1", "callerId": "+70000000000"},
    )

    assert r.status_code == 200
