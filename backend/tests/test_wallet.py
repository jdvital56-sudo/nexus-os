"""Тесты реестра сервисов и подписок (PR-26)."""
from datetime import date, timedelta

import pytest

from backend.services import wallet


def today_plus(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def test_service_is_added_with_defaults():
    s = wallet.add_service("DeepSeek", cost=2.0, period=wallet.PERIOD_PREPAID)

    assert s["name"] == "DeepSeek"
    assert s["status"] == wallet.STATUS_ACTIVE
    assert s["currency"] == "USD"
    assert s["balance"] is None


def test_duplicate_service_is_rejected():
    wallet.add_service("Midjourney")
    with pytest.raises(ValueError):
        wallet.add_service("midjourney")


def test_nameless_service_is_rejected():
    with pytest.raises(ValueError):
        wallet.add_service("   ")


def test_monthly_total_counts_yearly_as_twelfth():
    wallet.add_service("Месячный", cost=10, period=wallet.PERIOD_MONTHLY)
    wallet.add_service("Годовой", cost=120, period=wallet.PERIOD_YEARLY)

    assert wallet.monthly_total() == 20.0


def test_cancelled_service_leaves_the_bill():
    s = wallet.add_service("Ненужный", cost=30, period=wallet.PERIOD_MONTHLY)
    wallet.mark_cancelled(s["id"])

    assert wallet.monthly_total() == 0.0
    assert wallet.list_services() == []
    assert len(wallet.list_services(status=None)) == 1


def test_due_soon_finds_upcoming_charges():
    wallet.add_service("Завтра", cost=5, next_charge=today_plus(1))
    wallet.add_service("Через месяц", cost=5, next_charge=today_plus(30))

    due = wallet.due_soon()

    assert [s["name"] for s in due] == ["Завтра"]
    assert due[0]["days_left"] == 1


def test_overdue_charge_is_reported():
    wallet.add_service("Просрочено", cost=5, next_charge=today_plus(-2))

    due = wallet.due_soon()

    assert due[0]["days_left"] == -2


def test_broken_date_does_not_crash():
    wallet.add_service("Кривая дата", cost=5, next_charge="когда-нибудь")
    assert wallet.due_soon() == []


def test_low_balance_only_for_prepaid():
    wallet.add_service("Предоплата", cost=10, period=wallet.PERIOD_PREPAID)
    wallet.update_service("Предоплата", balance=0.5)
    wallet.add_service("Подписка", cost=10, period=wallet.PERIOD_MONTHLY)
    wallet.update_service("Подписка", balance=0.5)

    low = wallet.low_balance()

    assert [s["name"] for s in low] == ["Предоплата"]


def test_healthy_balance_is_not_flagged():
    wallet.add_service("Полный", cost=10, period=wallet.PERIOD_PREPAID)
    wallet.update_service("Полный", balance=9.0)

    assert wallet.low_balance() == []


def test_charge_date_advances_by_month():
    s = wallet.add_service("Месячный", cost=5, next_charge="2026-01-31")

    moved = wallet.advance_charge_date(s["id"])

    # 31 февраля не бывает — берём безопасное число
    assert moved["next_charge"] == "2026-02-28"


def test_charge_date_advances_by_year():
    s = wallet.add_service("Годовой", cost=50, period=wallet.PERIOD_YEARLY, next_charge="2026-03-10")

    assert wallet.advance_charge_date(s["id"])["next_charge"] == "2027-03-10"


def test_summary_lists_services_without_known_date():
    wallet.add_service("Без даты", cost=7)
    wallet.add_service("С датой", cost=7, next_charge=today_plus(20))

    assert wallet.summary()["unknown_charge_date"] == ["Без даты"]


# --- Деньги на счетах: ручной ввод и сводка (23.08.2026) ---


def test_balance_can_be_set_by_hand():
    """У Anthropic/fal.ai/Hetzner нет API остатка — без ручного ввода поле
    оставалось бы пустым навсегда."""
    s = wallet.add_service("fal.ai", cost=18, period=wallet.PERIOD_PREPAID)

    updated = wallet.update_service(s["id"], balance=12.5)

    assert updated["balance"] == 12.5
    assert updated["balance_checked_at"] is not None


def test_manual_balance_stamps_the_check_time():
    s = wallet.add_service("Anthropic", cost=24, period=wallet.PERIOD_PREPAID)
    assert wallet.get_service(s["id"])["balance_checked_at"] is None

    wallet.update_service(s["id"], balance=3.0)

    assert wallet.get_service(s["id"])["balance_checked_at"] is not None


def test_other_edits_do_not_touch_the_check_time():
    """Правка заметки не должна выдавать старый баланс за свежий."""
    s = wallet.add_service("DeepSeek", cost=2, period=wallet.PERIOD_PREPAID)
    wallet.update_service(s["id"], balance=1.98)
    stamped = wallet.get_service(s["id"])["balance_checked_at"]

    wallet.update_service(s["id"], notes="просто заметка")

    assert wallet.get_service(s["id"])["balance_checked_at"] == stamped


def test_prepaid_balance_sums_only_known_amounts():
    wallet.add_service("DeepSeek", cost=2, period=wallet.PERIOD_PREPAID)
    wallet.add_service("fal.ai", cost=18, period=wallet.PERIOD_PREPAID)
    wallet.add_service("Hetzner", cost=10, period=wallet.PERIOD_MONTHLY)
    wallet.update_service("DeepSeek", balance=1.98)

    prepaid = wallet.summary()["prepaid"]

    assert prepaid["total"] == 1.98
    assert prepaid["known"] == ["DeepSeek"]
    assert prepaid["unknown"] == ["fal.ai"]  # месячный Hetzner сюда не попадает


def test_prepaid_balance_flags_everything_unknown_when_nothing_entered():
    """Пустая сводка не должна читаться как «денег ноль» — должно быть
    видно, что цифры просто неизвестны."""
    wallet.add_service("fal.ai", cost=18, period=wallet.PERIOD_PREPAID)

    prepaid = wallet.summary()["prepaid"]

    assert prepaid["total"] == 0
    assert prepaid["unknown"] == ["fal.ai"]
    assert prepaid["known"] == []


@pytest.mark.asyncio
async def test_unknown_provider_has_no_balance_api():
    assert await wallet.fetch_balance("midjourney", "key") is None


@pytest.mark.asyncio
async def test_refresh_skips_services_without_key(monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "")
    wallet.add_service("DeepSeek", period=wallet.PERIOD_PREPAID, balance_provider="deepseek")

    assert await wallet.refresh_balances() == []


@pytest.mark.asyncio
async def test_refresh_records_balance(monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")

    async def fake_fetch(provider, api_key):
        return {"balance": 1.25, "currency": "USD", "available": True}

    monkeypatch.setattr(wallet, "fetch_balance", fake_fetch)
    wallet.add_service("DeepSeek", period=wallet.PERIOD_PREPAID, balance_provider="deepseek")

    updated = await wallet.refresh_balances()

    assert updated[0]["balance"] == 1.25
    assert updated[0]["balance_checked_at"]


@pytest.mark.asyncio
async def test_provider_failure_does_not_break_refresh(monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")

    async def boom(provider, api_key):
        raise RuntimeError("провайдер недоступен")

    monkeypatch.setattr(wallet, "fetch_balance", boom)
    wallet.add_service("DeepSeek", period=wallet.PERIOD_PREPAID, balance_provider="deepseek")

    assert await wallet.refresh_balances() == []


# --- HTTP API ---


def test_api_crud(client):
    created = client.post("/api/wallet", json={
        "name": "ElevenLabs", "cost": 22, "period": "monthly",
        "next_charge": today_plus(2), "cancel_url": "https://elevenlabs.io/subscription",
    })
    assert created.status_code == 201
    sid = created.json()["id"]

    assert client.get("/api/wallet").json()[0]["name"] == "ElevenLabs"
    assert client.put(f"/api/wallet/{sid}", json={"cost": 5}).json()["cost"] == 5
    assert client.post(f"/api/wallet/{sid}/cancelled").json()["status"] == "cancelled"


def test_api_summary_warns_about_upcoming(client):
    client.post("/api/wallet", json={"name": "Notion", "cost": 8, "next_charge": today_plus(1)})

    summary = client.get("/api/wallet/summary").json()

    assert summary["active_count"] == 1
    assert summary["due_soon"][0]["name"] == "Notion"


def test_api_rejects_duplicate(client):
    client.post("/api/wallet", json={"name": "Figma"})
    assert client.post("/api/wallet", json={"name": "figma"}).status_code == 400
