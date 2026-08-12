"""Время у фактов.

«Ставка клиента — 50 тысяч» было правдой до марта. Неверно не утверждение,
а его срок. Эти тесты проверяют, что система различает «неправда» и
«больше не действует» — и умеет отвечать на вопрос «как было тогда».
"""
from datetime import datetime, timedelta

import pytest

from backend.services import memory as mem_svc
from backend.services.memory import MemoryLayer


def _add(content="ставка 50 тысяч", since_days_ago: int | None = None, **kw):
    """Добавляет факт. since_days_ago открывает окно действия в прошлом.

    Без него окно начинается в момент записи — и это правильно: факт,
    записанный сегодня, сам по себе ничего не утверждает о вчерашнем дне.
    """
    fact = mem_svc.add_fact(content=content, layer=MemoryLayer.CANON, confidence=0.9, **kw)
    if since_days_ago is not None:
        started = (datetime.utcnow() - timedelta(days=since_days_ago)).isoformat()
        fact = mem_svc.update_fact(fact.id, valid_from=started)
    return fact


def now():
    return datetime.utcnow()


# === Поведение по умолчанию не изменилось ===


def test_fact_without_window_is_valid_now():
    fact = _add()
    assert fact.is_valid_at(now()) is True


def test_fact_says_nothing_about_the_day_before_it_was_recorded():
    """Запись сегодняшнего дня — не утверждение про вчера."""
    fact = _add()
    assert fact.is_valid_at(now() - timedelta(days=1)) is False


def test_fact_without_window_stays_active():
    assert _add().is_active is True


def test_old_facts_without_the_new_fields_still_work():
    """В памяти уже лежат факты, записанные до появления окна действия."""
    fact = _add()
    raw = mem_svc._load()
    for r in raw:
        r.pop("valid_from", None)
        r.pop("valid_until", None)
    mem_svc._save(raw)

    reloaded = mem_svc.get_fact(fact.id)
    assert reloaded.is_active is True
    assert reloaded.is_valid_at(now()) is True


# === Закрытие окна ===


def test_invalidate_closes_the_window_without_deleting():
    fact = _add()
    before = len(mem_svc._load())

    mem_svc.invalidate(fact.id)

    assert len(mem_svc._load()) == before, "факт не удаляется"
    assert mem_svc.get_fact(fact.id).content == "ставка 50 тысяч"
    assert mem_svc.get_fact(fact.id).is_active is False


def test_invalidated_fact_was_still_true_before():
    fact = _add(since_days_ago=30)
    mem_svc.invalidate(fact.id)
    assert mem_svc.get_fact(fact.id).is_valid_at(now() - timedelta(days=1)) is True


def test_invalidate_works_on_a_fact_saved_before_the_feature(monkeypatch):
    """Старые записи без новых полей тоже должны закрываться."""
    fact = _add()
    raw = mem_svc._load()
    for r in raw:
        r.pop("valid_until", None)
    mem_svc._save(raw)

    mem_svc.invalidate(fact.id)

    assert mem_svc.get_fact(fact.id).valid_until is not None
    assert mem_svc.get_fact(fact.id).is_active is False


def test_invalidate_at_a_chosen_moment():
    fact = _add(since_days_ago=60)
    closed_at = now() - timedelta(days=30)
    mem_svc.invalidate(fact.id, at=closed_at)

    reloaded = mem_svc.get_fact(fact.id)
    assert reloaded.is_valid_at(closed_at - timedelta(days=1)) is True
    assert reloaded.is_valid_at(now()) is False


# === Замена закрывает окно сама ===


def test_supersede_closes_the_old_window():
    old = _add("ставка 50 тысяч")
    new = mem_svc.supersede(old.id, "ставка 70 тысяч", confidence=0.9)

    old_after = mem_svc.get_fact(old.id)
    assert old_after.valid_until is not None
    assert old_after.superseded_by == new.id
    assert mem_svc.get_fact(new.id).is_active is True


def test_no_contradiction_between_old_and_new():
    """Две ставки не спорят — у них разные сроки."""
    old = _add("ставка 50 тысяч")
    mem_svc.supersede(old.id, "ставка 70 тысяч", confidence=0.9)

    active = [f.content for f in mem_svc.get_facts(active_only=True, limit=50)]
    assert active.count("ставка 50 тысяч") == 0
    assert "ставка 70 тысяч" in active


def test_history_survives_replacement():
    old = _add("ставка 50 тысяч")
    mem_svc.supersede(old.id, "ставка 70 тысяч", confidence=0.9)
    assert mem_svc.get_fact(old.id).content == "ставка 50 тысяч"


# === Взгляд в прошлое ===


def test_facts_as_of_returns_the_truth_of_that_day():
    old = _add("ставка 50 тысяч", since_days_ago=60)
    mem_svc.supersede(old.id, "ставка 70 тысяч", confidence=0.9)

    past = [f.content for f in mem_svc.facts_as_of(now() - timedelta(days=30))]
    assert "ставка 50 тысяч" in past, "в прошлом действовала старая ставка"
    assert "ставка 70 тысяч" not in past, "новая тогда ещё не существовала"


def test_facts_as_of_now_matches_current_truth():
    old = _add("ставка 50 тысяч")
    mem_svc.supersede(old.id, "ставка 70 тысяч", confidence=0.9)

    now = [f.content for f in mem_svc.facts_as_of(datetime.utcnow() + timedelta(seconds=1))]
    assert "ставка 70 тысяч" in now
    assert "ставка 50 тысяч" not in now


def test_future_fact_is_not_valid_yet():
    tomorrow = now() + timedelta(days=1)
    fact = _add()
    mem_svc.update_fact(fact.id, valid_from=tomorrow.isoformat())
    assert mem_svc.get_fact(fact.id).is_valid_at(now()) is False
    assert mem_svc.get_fact(fact.id).is_valid_at(tomorrow + timedelta(hours=1)) is True


# === Устойчивость ===


@pytest.mark.parametrize("field", ["valid_from", "valid_until"])
def test_broken_date_does_not_hide_the_fact(field):
    """Битая дата не должна прятать факт — это потеря данных молчком."""
    fact = _add()
    mem_svc.update_fact(fact.id, **{field: "не-дата"})
    assert mem_svc.get_fact(fact.id).is_valid_at(now()) is True


def test_invalidate_missing_fact_raises():
    from backend.core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        mem_svc.invalidate("нет-такого")
