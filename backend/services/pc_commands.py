"""Разбор голосовых команд компьютеру: плеер, громкость, окна, папки, питание.

25.08.2026. Почему отдельный модуль, а не ещё десяток регулярок в
`conversation.py`: этот файл — главное место столкновения параллельных
сессий (см. CLAUDE.md), и растить его на двести строк ради команд, которые
живут сами по себе, значит гарантированно устроить конфликт слияния.
`conversation.py` получает один метод `_try_pc`, всё остальное здесь.

Разбор без модели — та же дисциплина, что у `_try_open`/`_try_task`:
«пауза» обязана срабатывать мгновенно и одинаково, а не зависеть от
настроения LLM и не стоить денег. И то же правило про тишину: не узнали
команду — возвращаем None, фраза идёт в обычный разговор, а не упирается в
канцелярское «не понял».

Питание (сон/выключение/перезагрузка) сюда попадает, но само не
выполняется: уходит в `pending_action` и ждёт отдельного «подтверждаю» —
тем же путём, что рискованные клики из `computer_use.py`.
"""
import asyncio
import logging
import re

from . import media_control, system_control

logger = logging.getLogger(__name__)

# «на паузу», «поставь на паузу», «пауза». Окончание перебираем целиком:
# распознавание речи отдаёт то «пауза», то «паузу» — от того, услышало ли
# оно предлог перед словом.
_PAUSE = re.compile(r"^\s*(?:поставь\s+)?(?:на\s+)?пауз[ауе]?\s*[.!]?$", re.IGNORECASE)

# «продолжи», «продолжай», «играй дальше», «возобнови»
_RESUME = re.compile(
    r"^\s*(?:продолж(?:и|ай)|возобнови|играй(?:\s+дальше)?)"
    r"(?:\s+(?:музыку|трек|песню|воспроизведение))?\s*[.!]?$",
    re.IGNORECASE,
)

# «следующий трек», «следующую песню», «дальше», «переключи трек», «скипни»
_NEXT = re.compile(
    r"^\s*(?:(?:включи|поставь|давай|переключи)\s+)?"
    r"(?:следующ(?:ий|ую|ее)|друг(?:ой|ую)|скипни|скип)"
    r"(?:\s+(?:трек|песню|песня|композицию|музыку))?\s*[.!]?$",
    re.IGNORECASE,
)

# «предыдущий трек», «верни прошлую песню», «назад»
_PREV = re.compile(
    r"^\s*(?:(?:включи|поставь|верни|переключи)\s+)?"
    r"(?:предыдущ(?:ий|ую|ее)|прошл(?:ый|ую)|прежн(?:ий|юю))"
    r"(?:\s+(?:трек|песню|песня|композицию))?\s*[.!]?$",
    re.IGNORECASE,
)

# «останови музыку», «выключи музыку», «стоп музыку». Голое «стоп» сюда НЕ
# берём намеренно: это слово затыкает саму речь Джарвиса (перебивание,
# 23.08.2026), и отдавать его плееру значит сломать уже работающее.
_STOP_MUSIC = re.compile(
    r"^\s*(?:стоп|останови|выключи|заглуши|вырубай?|вырубь)\s+"
    r"(?:музыку|трек|песню|плеер|воспроизведение)\s*[.!]?$",
    re.IGNORECASE,
)

# «включи музыку» — не всегда «открой YouTube Music»: если плеер уже открыт
# и стоит на паузе, человек просит продолжить, а не вторую вкладку.
_PLAY_MUSIC = re.compile(
    r"^\s*(?:включи|поставь|запусти|давай)\s+музыку\s*[.!]?$", re.IGNORECASE
)

# «что играет», «что это за песня», «что сейчас играет»
_WHATS_PLAYING = re.compile(
    r"^\s*(?:что|какая|какой)\s+(?:сейчас\s+|это\s+|там\s+)?"
    r"(?:игра(?:ет|л)|за\s+(?:песня|трек|музыка)|песня|трек|музыка(?:\s+игра\w*)?)"
    r"\s*[?.!]?$",
    re.IGNORECASE,
)

# «громче», «сделай погромче», «прибавь звук»
_LOUDER = re.compile(
    r"^\s*(?:сделай\s+|стань\s+)?(?:по)?громче|^\s*приб(?:авь|авить)\s+(?:звук|громкость)",
    re.IGNORECASE,
)
_QUIETER = re.compile(
    r"^\s*(?:сделай\s+|стань\s+)?(?:по)?тише|^\s*убавь\s+(?:звук|громкость)",
    re.IGNORECASE,
)

# «поставь громкость 40», «громкость на 30 процентов», «звук на 50»
_VOLUME_LEVEL = re.compile(
    r"^\s*(?:(?:поставь|сделай|выстави|установи)\s+)?"
    r"(?:громкость|звук)\s*(?:на\s+)?(?P<level>\d{1,3})\s*(?:процент\w*|%)?\s*[.!]?$",
    re.IGNORECASE,
)

_MUTE = re.compile(
    r"^\s*(?:выключи|отключи|убери|заглуши)\s+(?:звук|громкость)\s*[.!]?$", re.IGNORECASE
)
_UNMUTE = re.compile(
    r"^\s*(?:включи|верни|восстанови)\s+(?:звук|громкость)\s*[.!]?$", re.IGNORECASE
)

# «какая громкость» — спросить, не менять
_VOLUME_QUERY = re.compile(
    r"^\s*(?:какая|какой)\s+(?:сейчас\s+)?(?:громкость|звук)\s*[?.!]?$", re.IGNORECASE
)

# === Окна, папки, состояние ===============================================

_CLOSE_APP = re.compile(
    r"^\s*(?:закрой|заверши|убери)\s+(?:окно\s+|программу\s+|приложение\s+)?"
    r"(?P<name>.+?)\s*[.!]?$",
    re.IGNORECASE,
)

_FOCUS_APP = re.compile(
    r"^\s*(?:переключись\s+на|перейди\s+(?:в|на)|покажи|открой\s+окно)\s+(?P<name>.+?)\s*[.!]?$",
    re.IGNORECASE,
)

_MINIMIZE_ALL = re.compile(
    r"^\s*(?:сверни\s+(?:вс[её]|все\s+окна)|покажи\s+рабочий\s+стол)\s*[.!]?$",
    re.IGNORECASE,
)

_LOCK = re.compile(
    r"^\s*(?:заблокируй|блокируй|запри)\s+(?:компьютер|экран|систему|комп)\s*[.!]?$",
    re.IGNORECASE,
)

_OPEN_FOLDER = re.compile(
    r"^\s*(?:открой|покажи|зайди\s+в)\s+(?:папку|каталог|директорию)\s+(?P<name>.+?)\s*[.!]?$",
    re.IGNORECASE,
)

_WHATS_OPEN = re.compile(
    r"^\s*(?:что|какие\s+окна|какие\s+программы)\s+(?:у\s+меня\s+)?(?:сейчас\s+)?"
    r"(?:открыт\w*|запущен\w*)\s*[?.!]?$",
    re.IGNORECASE,
)

_MACHINE_STATE = re.compile(
    r"^\s*(?:как\s+(?:там\s+)?компьютер|состояние\s+(?:компьютера|системы|машины)|"
    r"сколько\s+(?:свободн\w+\s+)?(?:памяти|места)|загрузка\s+системы)\s*[?.!]?$",
    re.IGNORECASE,
)

_CLIPBOARD_READ = re.compile(
    r"^\s*что\s+(?:у\s+меня\s+)?в\s+буфере(?:\s+обмена)?\s*[?.!]?$", re.IGNORECASE
)

_SCREENSHOT = re.compile(
    r"^\s*(?:сделай\s+|сними\s+)?(?:скриншот|снимок\s+экрана|скрин)\s*[.!]?$",
    re.IGNORECASE,
)

_CLIPBOARD_WRITE = re.compile(
    r"^\s*(?:скопируй|запиши)\s+в\s+буфер(?:\s+обмена)?\s*[:\-—]?\s*(?P<text>.+)$",
    re.IGNORECASE | re.DOTALL,
)

# === Питание ==============================================================

_POWER = re.compile(
    r"^\s*(?P<verb>выключи|отключи|перезагрузи|перезапусти|усыпи|засни)\s+"
    r"(?:компьютер|комп|систему|машину|ноутбук)\s*[.!]?$",
    re.IGNORECASE,
)

_POWER_CANCEL = re.compile(
    r"^\s*отмен(?:и|а)\s+(?:питани[ея]|выключени[ея]|перезагрузк[иу])\s*[.!]?$",
    re.IGNORECASE,
)

_POWER_VERBS = {
    "выключи": "shutdown",
    "отключи": "shutdown",
    "перезагрузи": "restart",
    "перезапусти": "restart",
    "усыпи": "sleep",
    "засни": "sleep",
}

# Шаг громкости. 10 — заметно на слух с первого раза: с 5 фаундеру
# пришлось бы говорить «громче» четыре раза подряд.
_VOLUME_STEP = 10


async def try_command(text: str, confirm_key: str = "") -> str | None:
    """Исполняет команду компьютеру. Не команда — возвращает None.

    `confirm_key` — ключ «канал:пользователь» для `pending_action`. Без него
    питание не предлагается вовсе: подтвердить его будет негде.
    """
    text = (text or "").strip()
    if not text:
        return None

    reply = await _try_player(text)
    if reply is not None:
        return reply

    reply = await asyncio.to_thread(_try_volume, text)
    if reply is not None:
        return reply

    reply = await asyncio.to_thread(_try_power, text, confirm_key)
    if reply is not None:
        return reply

    return await asyncio.to_thread(_try_windows, text)


async def _try_player(text: str) -> str | None:
    async def run(action: str) -> str:
        try:
            return await media_control.control(action)
        except media_control.NoPlayer as e:
            return str(e)

    if _PAUSE.match(text):
        return await run("pause")
    if _RESUME.match(text):
        return await run("play")
    if _NEXT.match(text):
        return await run("next")
    if _PREV.match(text):
        return await run("previous")
    if _STOP_MUSIC.match(text):
        return await run("pause")

    if _PLAY_MUSIC.match(text):
        # Плеер уже открыт — «включи музыку» значит «продолжи», а не «открой
        # вторую вкладку». Плеера нет — молчим, и system_open откроет
        # YouTube Music, как и раньше.
        current = await media_control.now_playing()
        if current is not None and current["is_player"]:
            return await run("play")
        return None

    if _WHATS_PLAYING.match(text):
        current = await media_control.now_playing()
        if current is None:
            return "Сейчас ничего не играет."
        name = media_control._describe(current)
        return f"Играет: {name}." if current["playing"] else f"На паузе: {name}."

    return None


def _try_volume(text: str) -> str | None:
    if _VOLUME_QUERY.match(text):
        state = media_control.get_volume()
        muted = " (звук выключен)" if state["muted"] else ""
        return f"Громкость {state['level']}%{muted}."

    match = _VOLUME_LEVEL.match(text)
    if match:
        return media_control.set_volume(int(match.group("level")))

    if _LOUDER.match(text):
        return media_control.nudge_volume(_VOLUME_STEP)
    if _QUIETER.match(text):
        return media_control.nudge_volume(-_VOLUME_STEP)
    if _MUTE.match(text):
        return media_control.set_mute(True)
    if _UNMUTE.match(text):
        return media_control.set_mute(False)
    return None


def _try_power(text: str, confirm_key: str) -> str | None:
    if _POWER_CANCEL.match(text):
        return system_control.power_cancel()

    match = _POWER.match(text)
    if not match:
        return None
    if not confirm_key:
        return None

    from . import pending_action

    action = _POWER_VERBS[match.group("verb").lower()]
    label = system_control.power_description(action)
    pending_action.hold(confirm_key, "power", {"action": action}, label)
    return f"Готов {label}. Скажите «подтверждаю» — сделаю, «отмена» — не буду."


def _try_windows(text: str) -> str | None:
    if _MINIMIZE_ALL.match(text):
        return system_control.minimize_all()
    if _LOCK.match(text):
        return system_control.lock()
    if _WHATS_OPEN.match(text):
        titles = system_control.list_windows()
        if not titles:
            return "Открытых окон не вижу."
        return f"Открыто окон: {len(titles)}. " + "; ".join(titles[:10])
    if _MACHINE_STATE.match(text):
        return system_control.describe_state()
    if _SCREENSHOT.match(text):
        return system_control.screenshot()
    if _CLIPBOARD_READ.match(text):
        content = system_control.clipboard_get()
        if not content:
            return "Буфер обмена пуст."
        short = content if len(content) <= 300 else content[:300] + "…"
        return f"В буфере: {short}"

    match = _CLIPBOARD_WRITE.match(text)
    if match:
        return system_control.clipboard_set(match.group("text").strip())

    match = _OPEN_FOLDER.match(text)
    if match:
        return system_control.open_folder(match.group("name"))

    # «закрой»/«покажи» — обычные глаголы, они встречаются в разговоре не
    # про окна («закрой вопрос», «покажи, что получилось»). Перехватываем
    # только когда такое окно ДЕЙСТВИТЕЛЬНО открыто — иначе тихо отдаём
    # None, ровно как _try_open с неизвестной целью.
    match = _CLOSE_APP.match(text)
    if match and system_control._match_windows(match.group("name")):
        return system_control.close_app(match.group("name"))

    match = _FOCUS_APP.match(text)
    if match and system_control._match_windows(match.group("name")):
        return system_control.focus_app(match.group("name"))

    return None
