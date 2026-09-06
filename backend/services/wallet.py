"""Реестр платных сервисов и подписок.

Отвечает на два вопроса, которые иначе теряются: за что я плачу и когда
с меня спишут снова. Где провайдер отдаёт баланс по API — цифра точная,
где нет — учитывается то, что известно, и это честно помечается.

Отменять подписки система не умеет и не будет: она напоминает и даёт
ссылку, решение и клик остаются за человеком (хартия §6, принцип 3).
"""
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..core.config import DATA_DIR, ensure_data_dir
from ..core.errors import NotFoundError
from ..core.jsonio import read_json, write_json

logger = logging.getLogger(__name__)

SERVICES_FILE = DATA_DIR / "services.json"

# Как устроена оплата
PERIOD_MONTHLY = "monthly"
PERIOD_YEARLY = "yearly"
PERIOD_PREPAID = "prepaid"   # платишь вперёд, тратится по мере использования
PERIOD_FREE = "free"
PERIODS = (PERIOD_MONTHLY, PERIOD_YEARLY, PERIOD_PREPAID, PERIOD_FREE)

STATUS_ACTIVE = "active"
STATUS_CANCELLED = "cancelled"

# За сколько дней до списания предупреждать
DEFAULT_WARN_DAYS = 3

# Ниже этой доли остатка считаем баланс тревожным
LOW_BALANCE_RATIO = 0.2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> list[dict]:
    ensure_data_dir()
    return read_json(SERVICES_FILE, []) or []


def _save(services: list[dict]) -> None:
    ensure_data_dir()
    write_json(SERVICES_FILE, services)


def add_service(
    name: str,
    category: str = "other",
    cost: float = 0.0,
    currency: str = "USD",
    period: str = PERIOD_MONTHLY,
    next_charge: str | None = None,
    cancel_url: str = "",
    url: str = "",
    balance_provider: str = "",
    notes: str = "",
) -> dict:
    """Добавить сервис в реестр."""
    if not name or not name.strip():
        raise ValueError("У сервиса должно быть название")

    services = _load()
    if any(s["name"].lower() == name.strip().lower() for s in services):
        raise ValueError(f"Сервис '{name}' уже в реестре")

    service = {
        "id": str(uuid.uuid4())[:8],
        "name": name.strip(),
        "category": category,
        "cost": float(cost),
        "currency": currency.upper(),
        "period": period if period in PERIODS else PERIOD_MONTHLY,
        "next_charge": next_charge,
        "cancel_url": cancel_url,
        "url": url,
        # Ключ провайдера, у которого баланс можно спросить по API
        "balance_provider": balance_provider,
        "balance": None,
        "balance_checked_at": None,
        "status": STATUS_ACTIVE,
        "notes": notes,
        "created_at": _now(),
    }
    services.append(service)
    _save(services)
    logger.info("В реестр добавлен сервис %s (%s %s/%s)", name, cost, currency, period)
    return service


def list_services(status: str | None = STATUS_ACTIVE) -> list[dict]:
    services = _load()
    if status:
        services = [s for s in services if s["status"] == status]
    return sorted(services, key=lambda s: (s["next_charge"] or "9999", s["name"]))


def get_service(service_id: str) -> dict:
    for s in _load():
        if s["id"] == service_id or s["name"].lower() == service_id.lower():
            return s
    raise NotFoundError("Service", service_id)


def update_service(service_id: str, **fields) -> dict:
    services = _load()
    for s in services:
        if s["id"] != service_id and s["name"].lower() != service_id.lower():
            continue
        for key, value in fields.items():
            if key in s and value is not None:
                s[key] = value
        # Баланс вписали руками — отмечаем когда, иначе на экране не отличить
        # свежую цифру от той, что фаундер вводил месяц назад (для сервисов
        # с API это делает refresh_balances, для остальных — только здесь)
        if fields.get("balance") is not None:
            s["balance_checked_at"] = _now()
        _save(services)
        return s
    raise NotFoundError("Service", service_id)


def mark_cancelled(service_id: str) -> dict:
    """Отметить, что человек отменил подписку. Сама система её не отменяет."""
    return update_service(service_id, status=STATUS_CANCELLED)


def remove_service(service_id: str) -> bool:
    services = _load()
    remaining = [s for s in services if s["id"] != service_id]
    if len(remaining) == len(services):
        raise NotFoundError("Service", service_id)
    _save(remaining)
    return True


def monthly_total(currency: str = "USD") -> float:
    """Во сколько обходится месяц по активным подпискам."""
    total = 0.0
    for s in list_services():
        if s["currency"] != currency or s["status"] != STATUS_ACTIVE:
            continue
        if s["period"] == PERIOD_MONTHLY:
            total += s["cost"]
        elif s["period"] == PERIOD_YEARLY:
            total += s["cost"] / 12
    return round(total, 2)


def _days_until(value: str | None) -> int | None:
    if not value:
        return None
    try:
        target = date.fromisoformat(value[:10])
    except ValueError:
        return None
    # Дата списания вписана по календарю фаундера, поэтому и «сегодня» здесь
    # местное. По UTC ночью получались сутки разницы: подписка, которая
    # спишется завтра, объявлялась как «через 2 дня».
    return (target - date.today()).days


def due_soon(warn_days: int = DEFAULT_WARN_DAYS) -> list[dict]:
    """Подписки, которые вот-вот спишутся — включая просроченные."""
    soon = []
    for s in list_services():
        days = _days_until(s.get("next_charge"))
        if days is not None and days <= warn_days:
            soon.append({**s, "days_left": days})
    return sorted(soon, key=lambda s: s["days_left"])


def low_balance() -> list[dict]:
    """Сервисы с предоплатой, где остаток подходит к концу."""
    low = []
    for s in list_services():
        balance = s.get("balance")
        if balance is None or s["period"] != PERIOD_PREPAID:
            continue
        # Тревожно, если остатка меньше пятой части типичного пополнения
        threshold = max(s["cost"] * LOW_BALANCE_RATIO, 1.0) if s["cost"] else 1.0
        if balance < threshold:
            low.append({**s, "threshold": round(threshold, 2)})
    return low


def advance_charge_date(service_id: str) -> dict:
    """Сдвинуть дату списания на следующий период — после того, как списали."""
    service = get_service(service_id)
    current = service.get("next_charge")
    if not current:
        return service
    try:
        base = date.fromisoformat(current[:10])
    except ValueError:
        return service

    if service["period"] == PERIOD_MONTHLY:
        month = base.month + 1
        year = base.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = min(base.day, 28)  # 29-31 числа не существуют в каждом месяце
        nxt = date(year, month, day)
    elif service["period"] == PERIOD_YEARLY:
        nxt = base.replace(year=base.year + 1)
    else:
        return service

    return update_service(service_id, next_charge=nxt.isoformat())


# --- Автоматическая проверка баланса ---


async def fetch_balance(provider: str, api_key: str) -> dict[str, Any] | None:
    """Спросить баланс у провайдера. None — провайдер этого не умеет."""
    import httpx

    if provider == "deepseek":
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                "https://api.deepseek.com/user/balance",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            r.raise_for_status()
            data = r.json()
            infos = data.get("balance_infos") or []
            if not infos:
                return None
            return {
                "balance": float(infos[0].get("total_balance", 0)),
                "currency": infos[0].get("currency", "USD"),
                "available": bool(data.get("is_available")),
            }

    logger.debug("Провайдер %s не отдаёт баланс по API", provider)
    return None


async def refresh_balances() -> list[dict]:
    """Обновить балансы всех сервисов, которые это поддерживают."""
    from ..core.config import settings

    keys = {
        "deepseek": settings.deepseek_api_key,
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
    }

    updated = []
    for service in list_services():
        provider = service.get("balance_provider")
        if not provider:
            continue
        api_key = keys.get(provider, "")
        if not api_key:
            logger.info("Нет ключа для %s — баланс не обновлён", provider)
            continue
        try:
            result = await fetch_balance(provider, api_key)
        except Exception:
            logger.warning("Не удалось узнать баланс %s", service["name"], exc_info=True)
            continue
        if not result:
            continue
        updated.append(
            update_service(
                service["id"],
                balance=result["balance"],
                balance_checked_at=_now(),
            )
        )
    return updated


def prepaid_balance(currency: str = "USD") -> dict:
    """Сколько всего лежит на предоплаченных счетах и по скольким сервисам
    цифра неизвестна.

    23.08.2026: фаундер сказал, что не видит, сколько у него денег. Сводка
    показывала только monthly_total — то есть один Hetzner: три сервиса из
    четырёх у него prepaid (Anthropic, DeepSeek, fal.ai), и деньги на них
    в сводку не попадали вообще. `unknown` важен не меньше суммы: без него
    «на счетах $1.98» читалось бы как полная картина, хотя это баланс
    одного DeepSeek, а про остальные просто ничего не известно.
    """
    total = 0.0
    known, unknown = [], []
    for s in list_services():
        if s["status"] != STATUS_ACTIVE or s["period"] != PERIOD_PREPAID:
            continue
        balance = s.get("balance")
        if balance is None or s["currency"] != currency:
            unknown.append(s["name"])
        else:
            total += float(balance)
            known.append(s["name"])
    return {"total": round(total, 2), "known": known, "unknown": unknown}


def digest_text() -> str:
    """Готовый текст сводки по ВСЕМ активным подпискам — для Telegram.

    24.08.2026, прямая просьба фаундера: «сделай напоминание в телеграм,
    причём всех подписок». Ежедневные тревоги (wallet_job) у него уже
    были, но по факту молчали: «скоро спишется» пусто, потому что дата
    указана только у ежемесячных, а он отменил единственную такую;
    «низкий баланс» пусто, потому что порог считается долей от суммы
    пополнения и для DeepSeek выходит $1.00 при остатке $1.94. Тревоги
    честные, но человек не видит вообще ничего и думает, что напоминаний
    нет. Сводка показывает всё как есть, тревога там или нет.
    """
    active = list_services()
    if not active:
        return "Активных подписок нет."

    s = summary()
    lines = [f"💳 Подписки — {len(active)} активных"]

    monthly = s["monthly_total_usd"]
    if monthly:
        lines.append(f"Уходит в месяц: ${monthly}")

    prepaid = s["prepaid"]
    if prepaid["known"]:
        lines.append(f"На предоплаченных счетах: ${prepaid['total']}")
    if prepaid["unknown"]:
        lines.append(f"Баланс неизвестен: {', '.join(prepaid['unknown'])}")

    lines.append("")
    alarming = {x["name"] for x in s["low_balance"]} | {x["name"] for x in s["due_soon"]}
    for item in sorted(active, key=lambda x: x["name"].lower()):
        mark = "⚠️ " if item["name"] in alarming else "· "
        parts = [f"{mark}{item['name']}"]

        if item["period"] == PERIOD_PREPAID:
            balance = item.get("balance")
            parts.append(f"остаток ${balance}" if balance is not None else "остаток неизвестен")
        else:
            parts.append(f"${item['cost']}/{item['period']}")

        days = _days_until(item.get("next_charge"))
        if days is not None:
            parts.append("списание сегодня" if days == 0 else (
                f"списание через {days} дн." if days > 0 else f"просрочено {-days} дн."
            ))
        lines.append(": ".join([parts[0], ", ".join(parts[1:])]) if len(parts) > 1 else parts[0])

    stale = [x["name"] for x in active
             if x["period"] == PERIOD_PREPAID and x.get("balance") is not None
             and _days_since(x.get("balance_checked_at")) is not None
             and _days_since(x.get("balance_checked_at")) > 7]
    if stale:
        lines.append("")
        lines.append(f"Цифры не обновлялись больше недели: {', '.join(stale)}")

    return "\n".join(lines)


def _days_since(value: str | None) -> int | None:
    """Сколько дней прошло с даты. Нужен, чтобы отличать свежую цифру
    баланса от той, что вписали месяц назад и забыли."""
    if not value:
        return None
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).days


def summary() -> dict:
    """Сводка для экрана и для утреннего брифа."""
    active = list_services()
    return {
        "active_count": len(active),
        "monthly_total_usd": monthly_total("USD"),
        "prepaid": prepaid_balance("USD"),
        "due_soon": due_soon(),
        "low_balance": low_balance(),
        "unknown_charge_date": [s["name"] for s in active if not s.get("next_charge")],
    }
