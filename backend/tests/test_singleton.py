"""Замок на единственное расписание (I-3).

2026-08-12 в три часа ночи фаундеру пришло три одинаковых брифа — по
одному на каждый запущенный бэкенд. Эти тесты держат оборону.
"""
import os

import pytest

from backend.core import singleton


def test_first_process_takes_the_lock():
    assert singleton.acquire("dream_cadence") is True
    assert singleton.holder_pid() == os.getpid()


def test_second_live_process_is_refused(monkeypatch):
    """Чужой живой процесс держит расписание — второй экземпляр молчит."""
    from backend.core.jsonio import write_json

    write_json(singleton.LOCK_FILE, {"pid": 999999, "name": "dream_cadence"})
    monkeypatch.setattr(singleton, "_alive", lambda pid: True)

    assert singleton.acquire() is False


def test_dead_holder_is_taken_over(monkeypatch):
    """Если бэкенд убили, следующий обязан подхватить расписание —
    иначе система молча перестанет будить по утрам."""
    from backend.core.jsonio import write_json

    write_json(singleton.LOCK_FILE, {"pid": 999999, "name": "dream_cadence"})
    monkeypatch.setattr(singleton, "_alive", lambda pid: False)

    assert singleton.acquire() is True
    assert singleton.holder_pid() == os.getpid()


def test_release_frees_the_lock():
    singleton.acquire()
    singleton.release()

    assert singleton.holder_pid() is None
    # После освобождения замок снова свободен
    assert singleton.acquire() is True


def test_release_does_not_touch_someone_elses_lock():
    from backend.core.jsonio import write_json

    write_json(singleton.LOCK_FILE, {"pid": 999999, "name": "dream_cadence"})
    singleton.release()

    assert singleton.holder_pid() == 999999


def test_same_process_can_reacquire():
    """Перезапуск расписания внутри одного процесса — не конфликт."""
    assert singleton.acquire() is True
    assert singleton.acquire() is True


@pytest.mark.asyncio
async def test_second_backend_does_not_schedule_jobs(monkeypatch):
    """Главное: второй экземпляр не ставит ни одной джобы."""
    from backend.agents.dream_cadence import DreamCadence

    monkeypatch.setattr(singleton, "acquire", lambda name="scheduler": False)
    cadence = DreamCadence()

    cadence.start()

    assert cadence.scheduler.running is False
    assert cadence.scheduler.get_jobs() == []


# --- Проверка живости на Windows (найдено сторожем 2026-08-12) ---


def test_own_process_is_alive():
    """os.kill(pid, 0) на Windows врал: на одних номерах срабатывал, на
    других бросал WinError 87. Из-за этого замок мог зависнуть."""
    assert singleton._alive(os.getpid()) is True


def test_absurd_pid_is_dead():
    assert singleton._alive(999999) is False


def test_nonpositive_pid_is_dead():
    assert singleton._alive(0) is False
    assert singleton._alive(-5) is False


def test_liveness_never_raises():
    """Сторож зовёт эту проверку в цикле — она не имеет права падать."""
    for pid in (1, 4, 12345, os.getpid(), 999999):
        assert singleton._alive(pid) in (True, False)
