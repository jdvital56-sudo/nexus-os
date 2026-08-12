"""Тесты сжатия контекста.

Главное здесь — не экономия, а безотказность: сжатие никогда не должно
уронить диалог и никогда не должно съесть реплику человека.
"""
import pytest

from backend.services import compression


def _long_logs(n=200):
    return "\n".join(
        f"2026-08-12 00:{i % 60:02d}:00 INFO agent=librarian step=observe docs=12 ok"
        for i in range(n)
    )


def _msgs(content=None):
    return [
        {"role": "user", "content": "Проанализируй логи и скажи, что пошло не так."},
        {"role": "assistant", "content": content or _long_logs()},
    ]


# === Выключено по умолчанию ===


def test_disabled_by_default(monkeypatch):
    monkeypatch.setattr(compression, "ENABLED", False)
    msgs = _msgs()
    out, stats = compression.compress_messages(msgs)
    assert out == msgs
    assert stats["applied"] is False


def test_empty_input_is_safe(monkeypatch):
    monkeypatch.setattr(compression, "ENABLED", True)
    assert compression.compress_messages([]) == ([], {"applied": False, "tokens_before": 0,
                                                     "tokens_after": 0, "saved": 0})


# === Безотказность ===


def test_missing_headroom_returns_original(monkeypatch):
    """Если библиотеки нет — работаем как раньше, без единой ошибки."""
    monkeypatch.setattr(compression, "ENABLED", True)
    import builtins

    real_import = builtins.__import__

    def no_headroom(name, *args, **kwargs):
        if name == "headroom":
            raise ImportError("нет такой библиотеки")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_headroom)

    msgs = _msgs()
    out, stats = compression.compress_messages(msgs)
    assert out == msgs
    assert stats["applied"] is False


def test_broken_headroom_does_not_crash(monkeypatch):
    """Сжатие — удобство, а не необходимость. Упасть из-за него нельзя."""
    monkeypatch.setattr(compression, "ENABLED", True)
    import headroom

    def boom(*a, **kw):
        raise RuntimeError("движок сжатия упал")

    monkeypatch.setattr(headroom, "compress", boom)

    msgs = _msgs()
    out, stats = compression.compress_messages(msgs)
    assert out == msgs, "исходные сообщения должны вернуться нетронутыми"
    assert stats["applied"] is False


def test_short_prompt_is_left_alone(monkeypatch):
    """На коротком запросе экономить нечего, а исказить смысл можно."""
    monkeypatch.setattr(compression, "ENABLED", True)
    msgs = [{"role": "user", "content": "Привет"}]
    out, stats = compression.compress_messages(msgs)
    assert out == msgs
    assert stats["applied"] is False


# === Работа по назначению ===


@pytest.mark.skipif(not compression.available(), reason="Headroom не установлен")
def test_long_context_gets_smaller(monkeypatch):
    monkeypatch.setattr(compression, "ENABLED", True)
    out, stats = compression.compress_messages(_msgs())

    assert stats["applied"] is True
    assert stats["tokens_after"] < stats["tokens_before"]
    assert stats["saved"] > 0
    assert len(out) == 2


@pytest.mark.skipif(not compression.available(), reason="Headroom не установлен")
def test_user_question_survives_compression(monkeypatch):
    """Режем объёмные данные, а не то, что сказал человек."""
    monkeypatch.setattr(compression, "ENABLED", True)
    question = "Проанализируй логи и скажи, что пошло не так."
    out, stats = compression.compress_messages(_msgs())

    assert stats["applied"] is True
    assert any(question in m["content"] for m in out), "вопрос человека должен уцелеть"


@pytest.mark.skipif(not compression.available(), reason="Headroom не установлен")
def test_roles_and_order_are_preserved(monkeypatch):
    monkeypatch.setattr(compression, "ENABLED", True)
    out, _ = compression.compress_messages(_msgs())
    assert [m["role"] for m in out] == ["user", "assistant"]


# === Оценка без отправки ===


@pytest.mark.skipif(not compression.available(), reason="Headroom не установлен")
def test_estimate_reports_savings_without_sending():
    report = compression.estimate(_msgs())
    assert report["available"] is True
    assert report["saved"] > 0
    assert 0 < report["ratio"] < 1


def test_estimate_on_empty_input():
    assert compression.estimate([]) == {"available": False}
