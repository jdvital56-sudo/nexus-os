"""Команды компьютеру, у которых нет своего дома в других сервисах.

25.08.2026, по прямой просьбе фаундера «Джарвис должен исполнять больше
команд на компьютере». Что уже было и сюда НЕ переезжает: открыть сайт или
программу — `system_open.py`; смотреть на экран, кликать и печатать —
`computer_use.py`; плеер и громкость — `media_control.py`. Здесь — окна,
папки, буфер обмена, состояние машины и питание.

**Граница безопасности.** Всё в этом файле обратимо, кроме питания. Закрыть
окно — это WM_CLOSE, то самое, что делает крестик: программа успевает
спросить «сохранить?» и может отказаться закрываться. Процессы здесь никто
не убивает: `TerminateProcess` потерял бы несохранённое, а команда голосом
слишком легко ослышивается, чтобы платить такую цену. Сон, выключение и
перезагрузка не выполняются сразу — они уходят в `pending_action` и ждут
отдельного «подтверждаю», как и рискованные клики.
"""
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Как фаундер называет папки вслух -> имя в реестре Windows. Через реестр,
# а не через склейку с домашней папкой: у него русская Windows, и часть
# папок перенесена — «Загрузки» не обязательно лежат в `~/Downloads`.
_SHELL_FOLDERS = {
    "загрузки": "{374DE290-123F-4565-9164-39C4925E467B}",
    "загрузку": "{374DE290-123F-4565-9164-39C4925E467B}",
    "скачанное": "{374DE290-123F-4565-9164-39C4925E467B}",
    "документы": "Personal",
    "рабочий стол": "Desktop",
    "стол": "Desktop",
    "изображения": "My Pictures",
    "картинки": "My Pictures",
    "фото": "My Pictures",
    "видео": "My Video",
    "музыка": "My Music",
    "музыку": "My Music",
}

# Свои папки — то, что открывается чаще системных. Абсолютные пути, а не
# поиск: «открой проекты» должно попадать в одно и то же место всегда.
_OWN_FOLDERS = {
    "проекты": Path.home() / "projects",
    "проект": Path.home() / "projects",
}

# Окна без заголовка — это невидимые служебные окна Windows, их в списке
# «что открыто» быть не должно: человек их не открывал и закрыть не просит.
_SKIP_WINDOW_TITLES = (
    "Program Manager",
    "Windows Input Experience",
    "Интерфейс ввода Windows",  # то же самое окно на русской Windows
)


class PowerAction(RuntimeError):
    """Питание не выполняется молча — нужен отдельный «подтверждаю»."""


# === Окна ==================================================================


def _windows_raw():
    import pygetwindow

    return [
        w
        for w in pygetwindow.getAllWindows()
        if w.title.strip() and w.title not in _SKIP_WINDOW_TITLES and w.width > 0
    ]


def list_windows() -> list[str]:
    """Заголовки открытых окон — ответ на «что у меня открыто»."""
    return [w.title.strip() for w in _windows_raw()]


def _match_windows(name: str) -> list:
    """Окна, чей заголовок содержит названное. Пусто — ничего не нашли.

    Ищем по подстроке: заголовок окна почти никогда не равен названию
    программы («Nexus OS — Google Chrome», «bot.py — nexus-os — Visual
    Studio Code»), а фаундер называет вслух саму программу.
    """
    from .system_open import SPOKEN_APP_NAMES

    q = name.strip().lower()
    q = SPOKEN_APP_NAMES.get(q, q)
    return [w for w in _windows_raw() if q in w.title.lower()]


def close_app(name: str) -> str:
    """Закрывает окно программы так же, как крестик: WM_CLOSE."""
    matches = _match_windows(name)
    if not matches:
        return f"Не вижу открытого окна «{name}». Проверьте, запущено ли оно."

    closed, failed = [], []
    for w in matches:
        try:
            w.close()
            closed.append(w.title.strip())
        except Exception as e:
            logger.warning("Окно %s не закрылось: %s", w.title, e)
            failed.append(w.title.strip())

    if not closed:
        return f"Не смог закрыть «{name}» — окно не отдало команду."
    reply = "Закрыл: " + ", ".join(closed[:3]) + ("…" if len(closed) > 3 else "") + "."
    if failed:
        reply += f" Не закрылось: {', '.join(failed[:3])}."
    # Программа могла спросить «сохранить изменения?» — тогда окно ещё на
    # экране. Честнее предупредить, чем отчитаться об успехе.
    return reply + " Если программа спросила про сохранение — она ждёт ответа на экране."


def focus_app(name: str) -> str:
    """Поднимает окно наверх — «переключись на хром»."""
    matches = _match_windows(name)
    if not matches:
        return f"Не вижу открытого окна «{name}»."
    w = matches[0]
    try:
        # Свёрнутое окно activate() не поднимает — сначала развернуть.
        if w.isMinimized:
            w.restore()
        w.activate()
    except Exception as e:
        # Windows не даёт поднять чужое окно, если фокусом владеет другой
        # процесс. Мигание в панели задач — то, что реально происходит.
        logger.warning("Окно %s не поднялось: %s", w.title, e)
        return f"«{w.title.strip()}» открыто, но Windows не отдала ему фокус — оно мигает в панели задач."
    return f"Переключился на {w.title.strip()}."


def minimize_all() -> str:
    """Свернуть всё — Win+D, тот же «показать рабочий стол»."""
    import pyautogui

    pyautogui.hotkey("win", "d")
    return "Свернул всё."


def lock() -> str:
    """Заблокировать компьютер. Обратимо: данные и программы остаются."""
    import ctypes

    if not ctypes.windll.user32.LockWorkStation():
        return "Не удалось заблокировать — Windows отказала."
    return "Блокирую."


# === Папки =================================================================


def _from_registry(key_name: str) -> Path | None:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ) as key:
            value, _ = winreg.QueryValueEx(key, key_name)
    except OSError:
        return None
    path = Path(os.path.expandvars(value))
    return path if path.is_dir() else None


def resolve_folder(name: str) -> Path | None:
    q = name.strip().lower().strip(".,!?")
    own = _OWN_FOLDERS.get(q)
    if own is not None and own.is_dir():
        return own
    key = _SHELL_FOLDERS.get(q)
    if key:
        return _from_registry(key)
    # Назвали полный путь — тоже законная команда: «открой папку C:\проекты»
    direct = Path(name.strip().strip('"'))
    return direct if direct.is_dir() else None


def open_folder(name: str) -> str:
    path = resolve_folder(name)
    if path is None:
        known = ", ".join(sorted(set(_SHELL_FOLDERS) | {"проекты"}))
        return f"Не знаю папку «{name}». Знаю такие: {known}."
    os.startfile(str(path))  # noqa: S606 — путь из реестра Windows, не из речи
    return f"Открываю {path}."


# === Буфер обмена ==========================================================


def clipboard_get() -> str:
    import pyperclip

    text = pyperclip.paste() or ""
    return text.strip()


def clipboard_set(text: str) -> str:
    import pyperclip

    pyperclip.copy(text)
    return f"Скопировал в буфер {len(text)} символов."


# === Снимок экрана =========================================================


def screenshot() -> str:
    """Снимок экрана файлом на рабочий стол.

    Не в папку артефактов, где лежит служебный мусор процесса: этот снимок
    человек просил для себя и пойдёт его искать глазами. Полный размер, а
    не ужатый под модель, — `computer_use.take_screenshot` уменьшает кадр
    до 1280 пикселей, чтобы сэкономить на токенах, и для человека это была
    бы порча картинки без причины.
    """
    from datetime import datetime

    import pyautogui

    folder = _from_registry("Desktop") or Path.home()
    out = folder / f"Экран {datetime.now():%Y-%m-%d %H-%M-%S}.png"
    pyautogui.screenshot().save(str(out))
    return f"Снимок экрана: {out}"


# === Состояние машины ======================================================


def machine_state() -> dict:
    """Заряд, память, диск, время работы — ответ на «как там компьютер»."""
    import time

    import psutil

    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.home().drive + "\\"))
    battery = psutil.sensors_battery()
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "ram_percent": mem.percent,
        "ram_free_gb": round(mem.available / 1024**3, 1),
        "disk_free_gb": round(disk.free / 1024**3, 1),
        "disk_percent": disk.percent,
        "battery_percent": round(battery.percent) if battery else None,
        "on_power": battery.power_plugged if battery else True,
        "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1),
    }


def describe_state() -> str:
    s = machine_state()
    parts = [
        f"Процессор {s['cpu_percent']:.0f}%",
        f"память занята на {s['ram_percent']:.0f}%, свободно {s['ram_free_gb']} ГБ",
        f"на диске свободно {s['disk_free_gb']} ГБ",
        f"работает {s['uptime_hours']} ч",
    ]
    if s["battery_percent"] is not None:
        power = "от сети" if s["on_power"] else "от батареи"
        parts.insert(0, f"Заряд {s['battery_percent']}% ({power})")
    return ". ".join(parts) + "."


# === Питание — только через подтверждение ==================================

POWER_ACTIONS = ("sleep", "shutdown", "restart")

_POWER_LABEL = {
    "sleep": "усыпить компьютер",
    "shutdown": "выключить компьютер",
    "restart": "перезагрузить компьютер",
}


def power_description(action: str) -> str:
    return _POWER_LABEL[action]


def power_confirmed(action: str) -> str:
    """Выполняет питание. Зовётся ТОЛЬКО после явного «подтверждаю»
    (conversation.py._try_confirm) — сама по себе команда сюда не доходит.

    Выключение и перезагрузка идут с задержкой в 20 секунд намеренно:
    `shutdown /a` в эти секунды всё отменяет, и человек, который передумал
    сразу после «подтверждаю», не теряет несохранённое.
    """
    if action not in POWER_ACTIONS:
        raise ValueError(f"Неизвестное действие питания: {action}")

    if action == "sleep":
        # Через SetSuspendState, а не `shutdown /h`: у фаундера включён
        # гибридный спящий режим, и `shutdown /h` при нём уходит в
        # гибернацию вместо сна.
        subprocess.run(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            check=False,
        )
        return "Усыпляю."

    flag = "/r" if action == "restart" else "/s"
    subprocess.run(["shutdown", flag, "/t", "20"], check=False)
    word = "Перезагружаю" if action == "restart" else "Выключаю"
    return f"{word} через 20 секунд. Скажите «отмена питания», если передумали."


def power_cancel() -> str:
    result = subprocess.run(["shutdown", "/a"], check=False, capture_output=True)
    if result.returncode != 0:
        return "Отменять нечего — выключение не запланировано."
    return "Отменил выключение."
