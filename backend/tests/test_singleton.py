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


# --- Замок бота: свой файл, не тот же, что у расписания (найдено 18.08.2026) ---


def test_bot_lock_is_a_different_file_from_scheduler_lock():
    """Гермес и расписание — разные процессы, им нельзя делить один замок."""
    assert singleton.BOT_LOCK_FILE != singleton.LOCK_FILE


def test_bot_lock_does_not_touch_the_scheduler_lock():
    assert singleton.acquire("dream_cadence") is True
    assert singleton.acquire_bot_lock() is True

    assert singleton.holder_pid() == os.getpid()
    assert singleton.bot_holder_pid() == os.getpid()


def test_second_bot_instance_is_refused(monkeypatch):
    """Второй Гермес выходит молча, а не дерётся с первым за getUpdates."""
    from backend.core.jsonio import write_json

    write_json(singleton.BOT_LOCK_FILE, {"pid": 999999, "name": "hermes_bot"})
    monkeypatch.setattr(singleton, "_alive", lambda pid: True)

    assert singleton.acquire_bot_lock() is False


def test_dead_bot_lock_is_taken_over(monkeypatch):
    from backend.core.jsonio import write_json

    write_json(singleton.BOT_LOCK_FILE, {"pid": 999999, "name": "hermes_bot"})
    monkeypatch.setattr(singleton, "_alive", lambda pid: False)

    assert singleton.acquire_bot_lock() is True
    assert singleton.bot_holder_pid() == os.getpid()


def test_bot_lock_release_frees_it():
    singleton.acquire_bot_lock()
    singleton.release_bot_lock()

    assert singleton.bot_holder_pid() is None


def test_truly_simultaneous_acquires_only_let_one_through(monkeypatch):
    """18.08.2026: read-then-write давал гонку — два процесса, стартовавшие
    в одну секунду, оба читали пустой файл до того, как другой успевал его
    записать, и оба решали, что они первые. Гоняем по-настоящему параллельно
    (не по очереди), чтобы доказать, что атомарное создание файла это
    закрывает, а не полагаться на то, что тест угадал тайминг.

    Потоки внутри одного теста делят один os.getpid() — значит без подмены
    каждый второй счёл бы себя «уже держащим свой же замок». Даём каждому
    потоку свой фальшивый pid, как будто это разные процессы."""
    import threading

    def fake_getpid():
        # id() потока как фальшивый номер процесса — разный на каждый поток,
        # реальный os.getpid() не участвует, поэтому конфликт не с самим собой
        return threading.get_ident() % 100000 + 1

    monkeypatch.setattr(singleton.os, "getpid", fake_getpid)
    monkeypatch.setattr(singleton, "_alive", lambda pid: True)

    results = []
    barrier = threading.Barrier(8)

    def attempt():
        barrier.wait()  # все восемь стартуют в один момент, не по очереди
        results.append(singleton._acquire_at(singleton.LOCK_FILE, "race"))

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 1
