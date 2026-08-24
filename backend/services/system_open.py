"""Открыть сайт или знакомую программу по голосовой/текстовой команде.

Шаг 2 из плана 19.08.2026: «Джарвис, открой ютуб» должно работать
одинаково из Телеграма, веб-чата и плавающего виджета — поэтому живёт
здесь, в общем конвейере (conversation.py зовёт это из handle()), а не в
одном из фронтендов по отдельности.

Важно для безопасности: сайты уходят в webbrowser.open — это открывает
ссылку в браузере по умолчанию, не выполняет произвольный код.

Программы (24.08.2026, по прямому решению фаундера «пусть открывает
любые»): ищем ЯРЛЫК в меню «Пуск» и запускаем его. Сырой расслышанный
текст по-прежнему никогда не уходит в subprocess как команда — мы лишь
ищем совпадение среди уже установленного на этой машине и запускаем
найденный .lnk. Ослышавшийся голос в худшем случае откроет не ту
программу из тех, что и так стоят у фаундера, но не выполнит
произвольный код и ничего не установит.

Границы, о которых договорились и которые тут НЕ трогаются: деньги,
отправка писем и необратимое остаются за человеком — за это отвечает
computer_use.py со своей проверкой рискованных кнопок.

Бэкенд крутится на той же машине, что и рабочий стол фаундера — открытие
происходит НА НЕЙ. Если команда пришла из Телеграма с телефона, сайт всё
равно откроется на домашнем компьютере, не на телефоне — так и задумано
(это тот же принцип, что у плавающего виджета), но об этом стоит помнить.
"""
import logging
import os
import re
import subprocess
import webbrowser
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# Меню «Пуск»: пользовательское и общесистемное. Отсюда берём список
# установленных программ — это то же, что видит человек, нажав «Пуск»,
# и там уже лежат готовые ярлыки со всеми нужными аргументами запуска.
START_MENU_DIRS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
]

# Куда вести по голому «включи музыку», без названия сервиса. YouTube
# Music, а не Spotify: он открывается в браузере без отдельной подписки и
# без установленного приложения — то есть сработает наверняка.
MUSIC_DEFAULT = "https://music.youtube.com"

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
    # Музыка (24.08.2026): фаундер сказал «включи музыку», Джарвис ответил
    # «не могу» — и был прав, музыкальных сервисов в этом списке не было
    # вовсе, команда не распознавалась и уходила в обычный разговор.
    "музыку": MUSIC_DEFAULT,
    "музыка": MUSIC_DEFAULT,
    "ютуб музыку": "https://music.youtube.com",
    "youtube music": "https://music.youtube.com",
    "спотифай": "https://open.spotify.com",
    "спотифай музыку": "https://open.spotify.com",
    "spotify": "https://open.spotify.com",
    "яндекс музыку": "https://music.yandex.ru",
    "яндекс музыка": "https://music.yandex.ru",
    "саундклауд": "https://soundcloud.com",
    "soundcloud": "https://soundcloud.com",
    "радио": "https://radio.garden",
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

# Слова, которые фаундер говорит вокруг названия, а не как название:
# «открой мне гугл хром пожалуйста» -> ищем «гугл хром».
_FILLER = re.compile(
    r"\b(?:мне|пожалуйста|давай|программу|приложение|прогу|app)\b",
    re.IGNORECASE,
)


# Как фаундер называет программы вслух -> как они называются в ярлыке.
# Он говорит по-русски, а ярлыки в «Пуске» почти все латиницей: без этой
# таблицы «открой хром» не находило ничего (проверено 24.08.2026 на его
# реальном списке из 100 программ).
SPOKEN_APP_NAMES: dict[str, str] = {
    "хром": "chrome",
    "гугл хром": "chrome",
    "хроме": "chrome",
    "опера": "opera",
    "оперу": "opera",
    "эдж": "edge",
    "телеграм": "telegram",
    "телеграмм": "telegram",
    "телегу": "telegram",
    "скайп": "skype",
    "зум": "zoom",
    "дискорд": "discord",
    "стим": "steam",
    "обс": "obs",
    "обс студио": "obs",
    "обсидиан": "obsidian",
    "код": "visual studio code",
    "вс код": "visual studio code",
    "студио код": "visual studio code",
    "блокнот++": "notepad++",
    "терминал": "windows powershell",
    "повершелл": "windows powershell",
    "командную строку": "command prompt",
    "диспетчер задач": "task manager",
    "панель управления": "control panel",
    "проигрыватель": "windows media player legacy",
    "клод": "claude",
    "гит": "git bash",
    "стор": "microsoft store",
    "магазин": "microsoft store",
}


@lru_cache(maxsize=1)
def _installed_apps() -> dict[str, Path]:
    """Ярлыки из меню «Пуск»: имя в нижнем регистре -> путь к .lnk.

    Кэш на весь процесс: обход двух папок стоит десятки миллисекунд, а
    список программ между перезапусками бэкенда меняется редко. Поставили
    новую программу и хотите, чтобы Джарвис её увидел — перезапустите
    бэкенд или позовите forget_installed_apps().
    """
    found: dict[str, Path] = {}
    for root in START_MENU_DIRS:
        if not root.is_dir():
            continue
        for lnk in root.rglob("*.lnk"):
            found.setdefault(lnk.stem.lower(), lnk)
    logger.info("Меню «Пуск»: найдено %d программ", len(found))
    return found


def forget_installed_apps() -> None:
    """Сбросить кэш списка программ — после установки чего-то нового."""
    _installed_apps.cache_clear()


def _find_app(q: str) -> Path | None:
    """Ищет программу по названию: точное совпадение, потом вхождение.

    Вхождение нужно, потому что ярлыки называются длиннее, чем люди
    говорят: «телеграм» против «Telegram Desktop», «хром» против
    «Google Chrome». Из нескольких совпадений берём самое короткое имя —
    оно почти всегда и есть сама программа, а не её деинсталлятор или
    «Читать первым.lnk» рядом.
    """
    apps = _installed_apps()
    if q in apps:
        return apps[q]

    # «хром» -> «chrome»: без этого русское произношение не находило
    # латинские ярлыки, а их в «Пуске» подавляющее большинство.
    q = SPOKEN_APP_NAMES.get(q, q)
    if q in apps:
        return apps[q]

    # Деинсталляторы лежат в том же меню и часто короче по имени, чем сама
    # программа — запустить их вместо неё было бы бедой.
    def usable(name: str) -> bool:
        return not any(bad in name for bad in ("uninstall", "деинсталл", "удалить"))

    # Сначала совпадение по ЦЕЛОМУ слову: «обс» -> «obs studio», а не
    # «obsidian». По длине сортировать тут нельзя — «obsidian» короче, и
    # именно так первая версия открывала не ту программу (24.08.2026).
    word = re.compile(rf"\b{re.escape(q)}\b")
    by_word = [(n, p) for n, p in apps.items() if usable(n) and word.search(n)]
    if by_word:
        by_word.sort(key=lambda pair: len(pair[0]))
        return by_word[0][1]

    matches = [(n, p) for n, p in apps.items() if usable(n) and q in n]
    if not matches:
        return None
    matches.sort(key=lambda pair: len(pair[0]))
    return matches[0][1]


def resolve(query: str) -> tuple[str, str] | None:
    """Возвращает ('site', url) | ('app', команда) | None, если не понял."""
    q = query.strip().lower().strip(".,!?—-")
    q = _FILLER.sub("", q).strip()
    if not q:
        return None

    # Названо как программа («телеграм», «хром») и она реально установлена —
    # открываем её, а не сайт: настольное приложение почти всегда то, что
    # человек имел в виду, раз оно у него стоит. Веб-версия остаётся
    # запасным вариантом ниже, если программы нет.
    if q in SPOKEN_APP_NAMES:
        lnk = _find_app(q)
        if lnk is not None:
            return ("shortcut", str(lnk))

    if q in SITE_ALIASES:
        return ("site", SITE_ALIASES[q])
    if q in APP_ALIASES:
        return ("app", APP_ALIASES[q])
    if _URL_LIKE.match(q):
        url = q if q.startswith("http") else f"https://{q}"
        return ("site", url)

    lnk = _find_app(q)
    if lnk is not None:
        return ("shortcut", str(lnk))
    return None


def open_target(query: str) -> str:
    """Открывает сайт/программу на этой машине. Возвращает, что ответить."""
    resolved = resolve(query)
    if resolved is None:
        return (
            f"Не нашёл, что открывать — «{query}». Такой программы нет в меню "
            f"«Пуск», и на сайт это не похоже. Скажите точнее или назовите адрес."
        )

    kind, target = resolved
    try:
        if kind == "site":
            webbrowser.open(target)
            return f"Открываю {target}."
        if kind == "shortcut":
            # Ярлык запускаем через оболочку Windows (os.startfile) — она
            # сама разбирает .lnk со всеми его аргументами и рабочей
            # папкой. subprocess.Popen на .lnk не работает: это не exe.
            os.startfile(target)  # noqa: S606 — путь из меню «Пуск», не из речи
            return f"Запускаю {Path(target).stem}."
        subprocess.Popen([target])
        return f"Запускаю {query}."
    except Exception as e:
        logger.exception("Не удалось открыть %s", target)
        return f"Не получилось открыть «{query}»: {e}"
