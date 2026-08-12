"""Замок на единственный экземпляр фоновых расписаний (инвариант I-3).

Ночной прогон, утреннее напоминание и автопилот живут в APScheduler внутри
процесса приложения. Если запущено два бэкенда — а это бывает: второй порт
для проверки, забытое окно терминала, `--workers 2` — расписание работает в
каждом, и человек получает три одинаковых сообщения в три часа ночи.

Так и случилось 2026-08-12: три копии брифа, по одной на каждый живой
бэкенд. Инвариант был записан в комментарии, но ничего его не удерживало.

Замок — файл с номером процесса. Мёртвый номер перехватывается: если
предыдущий бэкенд убит, новый обязан подхватить расписание, иначе система
молча перестанет будить фаундера по утрам.
"""
import logging
import os
import sys
from pathlib import Path

from .config import DATA_DIR, ensure_data_dir
from .jsonio import read_json, write_json

logger = logging.getLogger(__name__)

LOCK_FILE = DATA_DIR / "scheduler.lock"


def _alive(pid: int) -> bool:
    """Жив ли процесс с таким номером. Чужой процесс считаем живым.

    На Windows `os.kill(pid, 0)` для проверки не годится: на одних номерах
    он молча срабатывает, на других бросает WinError 87 и даже SystemError.
    Сторож поймал это в первый же прогон. Поэтому под Windows спрашиваем
    систему напрямую, а os.kill остаётся для остальных платформ.
    """
    if pid <= 0:
        return False

    if sys.platform == "win32":
        import ctypes

        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        # Отказ в доступе означает, что процесс есть, просто он не наш
        ERROR_ACCESS_DENIED = 5
        return ctypes.windll.kernel32.GetLastError() == ERROR_ACCESS_DENIED

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Процесс есть, но не наш — значит точно живой
        return True
    except OSError:
        return False
    return True


def acquire(name: str = "scheduler") -> bool:
    """Пытается занять замок. True — расписание наше, False — уже занято."""
    ensure_data_dir()
    holder = read_json(LOCK_FILE, {}) or {}
    pid = int(holder.get("pid", 0) or 0)

    if pid and pid != os.getpid() and _alive(pid):
        logger.warning(
            "Расписание %s уже ведёт процесс %s — здесь оно не запускается. "
            "Иначе напоминания придут дважды.",
            name,
            pid,
        )
        return False

    write_json(LOCK_FILE, {"pid": os.getpid(), "name": name})
    return True


def release() -> None:
    """Отпускает замок, если он наш. Чужой не трогаем."""
    holder = read_json(LOCK_FILE, {}) or {}
    if int(holder.get("pid", 0) or 0) == os.getpid():
        Path(LOCK_FILE).unlink(missing_ok=True)


def holder_pid() -> int | None:
    """Кто сейчас держит расписание. Для диагностики и /api/system/status."""
    holder = read_json(LOCK_FILE, {}) or {}
    pid = int(holder.get("pid", 0) or 0)
    return pid or None
