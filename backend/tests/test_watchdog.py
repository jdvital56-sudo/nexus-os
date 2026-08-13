"""Сторож: следит за системой и молчит, пока всё хорошо.

Два правила, ради которых он написан именно так, и проверяются здесь:
модель он не трогает вообще, а сообщает только на смену состояния.
"""
import pytest

from backend.services import watchdog


def test_report_covers_the_basics():
    report = watchdog.run()
    ids = {c["id"] for c in report["checks"]}

    assert {"data_dir", "disk", "llm", "memory", "scheduler", "budget"} <= ids
    assert isinstance(report["healthy"], bool)


def test_broken_check_does_not_kill_the_watchdog(monkeypatch):
    """Упавшая проверка — это тоже находка, а не конец прогона."""

    def boom():
        raise RuntimeError("проверка сломалась")

    monkeypatch.setattr(watchdog, "CHECKS", (boom, watchdog._check_disk))

    report = watchdog.run()

    assert report["healthy"] is False
    assert len(report["checks"]) == 2


def test_watchdog_never_calls_the_model(monkeypatch):
    """Главное правило: сторож обязан работать, когда модель недоступна."""
    from backend.services.llm import LLMService

    async def forbidden(*args, **kwargs):
        raise AssertionError("сторож полез в модель — так нельзя")

    monkeypatch.setattr(LLMService, "generate_response", forbidden)
    monkeypatch.setattr(LLMService, "chat", forbidden)

    report = watchdog.run()

    assert "checks" in report


@pytest.mark.asyncio
async def test_first_run_reports_only_breakage(monkeypatch):
    sent = []

    monkeypatch.setattr(
        watchdog,
        "CHECKS",
        (lambda: watchdog.Check("проба", "Проба", False, "сломано", critical=True),),
    )

    await watchdog.check_and_notify(send=lambda text: _collect(sent, text))

    assert sent and "Сломалось" in sent[0]


@pytest.mark.asyncio
async def test_silence_when_nothing_changed(monkeypatch):
    """Продолжает быть сломанным — сторож молчит. Иначе это спам, и человек
    перестанет читать уведомления."""
    sent = []
    monkeypatch.setattr(
        watchdog, "CHECKS", (lambda: watchdog.Check("проба", "Проба", False, "сломано"),)
    )

    await watchdog.check_and_notify(send=lambda text: _collect(sent, text))
    await watchdog.check_and_notify(send=lambda text: _collect(sent, text))

    assert len(sent) == 1


@pytest.mark.asyncio
async def test_recovery_is_reported(monkeypatch):
    sent = []
    monkeypatch.setattr(
        watchdog, "CHECKS", (lambda: watchdog.Check("проба", "Проба", False, "сломано"),)
    )
    await watchdog.check_and_notify(send=lambda text: _collect(sent, text))

    monkeypatch.setattr(
        watchdog, "CHECKS", (lambda: watchdog.Check("проба", "Проба", True, "работает"),)
    )
    await watchdog.check_and_notify(send=lambda text: _collect(sent, text))

    assert len(sent) == 2
    assert "Починилось" in sent[1]


@pytest.mark.asyncio
async def test_healthy_system_stays_quiet(monkeypatch):
    sent = []
    monkeypatch.setattr(
        watchdog, "CHECKS", (lambda: watchdog.Check("проба", "Проба", True, "работает"),)
    )

    report = await watchdog.check_and_notify(send=lambda text: _collect(sent, text))

    assert sent == []
    assert report["notified"] is False


@pytest.mark.asyncio
async def test_send_failure_does_not_break_the_check(monkeypatch):
    """Телеграм недоступен — состояние всё равно должно запомниться."""
    monkeypatch.setattr(
        watchdog, "CHECKS", (lambda: watchdog.Check("проба", "Проба", False, "сломано"),)
    )

    async def broken_send(text):
        raise RuntimeError("телеграм недоступен")

    report = await watchdog.check_and_notify(send=broken_send)

    assert report["healthy"] is False
    assert watchdog._load_state()["checks"]["проба"] is False


def test_api_report(client, monkeypatch):
    """heal=True на этом эндпоинте не должен поднимать настоящий APScheduler
    в тестовом процессе — он один на весь прогон pytest и пережил бы этот тест."""
    from backend.agents.dream_cadence import dream_cadence

    monkeypatch.setattr(dream_cadence, "start", lambda: None)

    r = client.get("/api/system/health-report")

    assert r.status_code == 200
    assert "checks" in r.json()


def test_heal_recovers_a_dead_scheduler_lock(monkeypatch):
    """Мёртвый замок — сторож перехватывает расписание сам, не дожидаясь
    перезапуска бэкенда (раньше только находил, теперь и чинит)."""
    from backend.agents.dream_cadence import dream_cadence

    healed = {"done": False}

    def fake_start():
        healed["done"] = True

    monkeypatch.setattr(dream_cadence, "start", fake_start)
    monkeypatch.setattr(
        watchdog,
        "_check_scheduler",
        lambda: watchdog.Check("scheduler", "Расписание", healed["done"], "проба", critical=True),
    )
    monkeypatch.setattr(watchdog, "CHECKS", (watchdog._check_scheduler,))

    report = watchdog.run(heal=True)

    assert healed["done"] is True
    assert report["healthy"] is True


def test_heal_is_off_by_default(monkeypatch):
    """Без heal=True сторож только докладывает — ничего не трогает."""
    from backend.agents.dream_cadence import dream_cadence

    called = []
    monkeypatch.setattr(dream_cadence, "start", lambda: called.append(1))
    monkeypatch.setattr(
        watchdog,
        "CHECKS",
        (lambda: watchdog.Check("scheduler", "Расписание", False, "мёртв", critical=True),),
    )

    report = watchdog.run()

    assert called == []
    assert report["healthy"] is False


def test_heal_failure_does_not_crash_the_check(monkeypatch):
    """Если сама попытка починить упала — отчёт остаётся тем, что было."""
    from backend.agents.dream_cadence import dream_cadence

    def boom():
        raise RuntimeError("не вышло")

    monkeypatch.setattr(dream_cadence, "start", boom)
    monkeypatch.setattr(
        watchdog,
        "CHECKS",
        (lambda: watchdog.Check("scheduler", "Расписание", False, "мёртв", critical=True),),
    )

    report = watchdog.run(heal=True)

    assert report["healthy"] is False


async def _collect(bucket: list, text: str) -> None:
    bucket.append(text)
