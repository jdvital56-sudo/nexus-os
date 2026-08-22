"""Открыть сайт или знакомую программу по голосовой/текстовой команде.

Шаг 2 из плана 19.08.2026: «Джарвис, открой ютуб» должно работать
одинаково из Телеграма, веб-чата и плавающего виджета — поэтому живёт
здесь, в общем конвейере (conversation.py зовёт это из handle()), а не в
одном из фронтендов по отдельности.

Важно для безопасности: сайты уходят в webbrowser.open — это открывает
ссылку в браузере по умолчанию, не выполняет произвольный код. Программы —
только из жёстко зашитого списка APP_ALIASES ниже; сырой расслышанный
текст никогда не уходит в subprocess напрямую — иначе ослышавшийся голос
мог бы попытаться запустить что угодно с именем случайного файла.

Бэкенд крутится на той же машине, что и рабочий стол фаундера — открытие
происходит НА НЕЙ. Если команда пришла из Телеграма с телефона, сайт всё
равно откроется на домашнем компьютере, не на телефоне — так и задумано
(это тот же принцип, что у плавающего виджета), но об этом стоит помнить.
"""
import logging
import re
import subprocess
import webbrowser

logger = logging.getLogger(__name__)

# Название сайта по-русски/по-английски -> адрес. Дополнять по мере нужды.
SITE_ALIASES: dict[str, str] = {
    "ютуб": "https://youtube.com",
    "youtube": "https://youtube.com",
    "гугл": "https://google.com",
    "google": "https://google.com",
    "гмайл": "https://mail.google.com",
    "почту": "https://mail.google.com",
    "почта": "https://mail.google.com",
    "телеграм": "https://web.telegram.org",
    "телеграмм": "https://web.telegram.org",
    "гитхаб": "https://github.com",
    "github": "https://github.com",
    "капкат": "https://capcut.com",
    "capcut": "https://capcut.com",
}

# Программа по-русски -> команда Windows. Только эти — никогда не берём
# расслышанный текст напрямую, только известные безопасные записи.
APP_ALIASES: dict[str, str] = {
    "калькулятор": "calc",
    "блокнот": "notepad",
    "проводник": "explorer",
    "паинт": "mspaint",
    "paint": "mspaint",
}

_URL_LIKE = re.compile(r"^(https?://)?[\w-]+\.[a-z]{2,}(/\S*)?$", re.IGNORECASE)


def resolve(query: str) -> tuple[str, str] | None:
    """Возвращает ('site', url) | ('app', команда) | None, если не понял."""
    q = query.strip().lower().strip(".,!?—-")
    if not q:
        return None

    if q in SITE_ALIASES:
        return ("site", SITE_ALIASES[q])
    if q in APP_ALIASES:
        return ("app", APP_ALIASES[q])
    if _URL_LIKE.match(q):
        url = q if q.startswith("http") else f"https://{q}"
        return ("site", url)
    return None


def open_target(query: str) -> str:
    """Открывает сайт/программу на этой машине. Возвращает, что ответить."""
    resolved = resolve(query)
    if resolved is None:
        known_apps = ", ".join(sorted(APP_ALIASES))
        return (
            f"Не понял, что открывать — «{query}». Могу открыть сайт по адресу "
            f"(например «открой github.com») или программу: {known_apps}."
        )

    kind, target = resolved
    try:
        if kind == "site":
            webbrowser.open(target)
            return f"Открываю {target}."
        subprocess.Popen([target])
        return f"Запускаю {query}."
    except Exception as e:
        logger.exception("Не удалось открыть %s", target)
        return f"Не получилось открыть «{query}»: {e}"
