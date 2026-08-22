"""Хранилище заблокированных действий, ждущих «подтверждаю»."""
import pytest

from backend.services import pending_action as pa


@pytest.fixture(autouse=True)
def clean_store():
    """Общий модульный словарь — не должен утекать между тестами."""
    pa._store.clear()
    yield
    pa._store.clear()


def test_get_returns_none_when_nothing_pending():
    assert pa.get("telegram:42") is None


def test_hold_then_get_returns_same_action():
    pa.hold("telegram:42", "click", {"x": 1, "y": 2, "label": "Оплатить"}, "описание")

    action = pa.get("telegram:42")

    assert action is not None
    assert action.kind == "click"
    assert action.payload == {"x": 1, "y": 2, "label": "Оплатить"}


def test_keys_are_isolated_per_channel_user():
    pa.hold("telegram:42", "click", {"x": 1, "y": 2, "label": ""}, "")

    assert pa.get("web:42") is None
    assert pa.get("telegram:99") is None


def test_new_hold_replaces_old_pending_action():
    pa.hold("telegram:42", "click", {"x": 1, "y": 2, "label": "первый"}, "")
    pa.hold("telegram:42", "type", {"text": "второй", "label": ""}, "")

    action = pa.get("telegram:42")

    assert action.kind == "type"
    assert action.payload["text"] == "второй"


def test_clear_removes_pending_action():
    pa.hold("telegram:42", "click", {"x": 1, "y": 2, "label": ""}, "")

    pa.clear("telegram:42")

    assert pa.get("telegram:42") is None


def test_clear_on_missing_key_does_not_raise():
    pa.clear("telegram:nope")  # не должно бросить


def test_action_expires_after_ttl(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(pa.time, "monotonic", lambda: clock["t"])

    pa.hold("telegram:42", "click", {"x": 1, "y": 2, "label": ""}, "")
    clock["t"] += pa.TTL_SECONDS + 1

    assert pa.get("telegram:42") is None


def test_action_survives_within_ttl(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(pa.time, "monotonic", lambda: clock["t"])

    pa.hold("telegram:42", "click", {"x": 1, "y": 2, "label": ""}, "")
    clock["t"] += pa.TTL_SECONDS - 1

    assert pa.get("telegram:42") is not None
