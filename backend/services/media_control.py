"""Управление тем, что играет, и громкостью этой машины.

25.08.2026, по прямой просьбе фаундера: раньше система умела только
ОТКРЫТЬ YouTube Music (system_open.py), но не управлять им — «пауза»,
«следующий трек» уходили в обычный разговор с моделью, и Джарвис на них
отвечал словами вместо действия.

**Почему не медиа-клавиши как основной путь.** Очевидное решение — послать
VK_MEDIA_PLAY_PAUSE через pyautogui. Оно работает, но идёт в ту сессию,
которую Windows считает текущей, а её выбирает не человек. На этой машине
в момент разработки активных сессий было две: Chrome (YouTube Music) и
Telegram Desktop — и «следующий трек» перемотал бы голосовое сообщение в
Телеграме, а не песню. Проверено живьём, не предположено.

Поэтому основной путь — WinRT `GlobalSystemMediaTransportControls`: он
показывает ВСЕ сессии по именам приложений, и командой можно попасть
именно в нужную. Заодно он единственный, кто умеет ответить на вопрос
«что сейчас играет» — медиа-клавиши обратной связи не дают вовсе.
Медиа-клавиши остаются запасным путём, если WinRT недоступен.

Громкость — отдельный интерфейс Windows (pycaw/IAudioEndpointVolume), а не
клавиши: клавиша меняет громкость шагом «сколько-то», а фаундер может
сказать «поставь громкость сорок» — это уровень, а не шаг.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

# Статусы WinRT PlaybackStatus. Держим числами: перечисление приходит из
# winsdk, а модуль обязан отвечать что-то осмысленное и когда winsdk нет.
_PLAYING = 4

# Приложения, которые держат медиа-сессию, но музыкой не являются. Телеграм
# заводит сессию на каждое голосовое сообщение и часто оказывается
# «текущим» — именно из-за него команда уходила не туда (см. шапку файла).
_NOT_A_PLAYER = ("telegram", "whatsapp", "discord", "zoom", "skype")

ACTIONS = ("play", "pause", "toggle", "next", "previous", "stop")


class NoPlayer(RuntimeError):
    """Играть нечем: ни одной медиа-сессии на машине."""


def _is_player(app: str) -> bool:
    low = (app or "").lower()
    return not any(bad in low for bad in _NOT_A_PLAYER)


async def _manager():
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )

    return await Manager.request_async()


async def sessions() -> list[dict]:
    """Все медиа-сессии машины: кто, что и играет ли прямо сейчас."""
    try:
        mgr = await _manager()
    except Exception as e:
        logger.warning("WinRT медиа-сессии недоступны: %s", e)
        return []

    out: list[dict] = []
    for s in mgr.get_sessions():
        try:
            info = await s.try_get_media_properties_async()
            status = int(s.get_playback_info().playback_status)
        except Exception:
            # Сессия могла закрыться между перечислением и опросом — это
            # норма, а не поломка: просто пропускаем её.
            continue
        app = s.source_app_user_model_id or ""
        out.append(
            {
                "app": app,
                "title": (info.title or "").strip(),
                "artist": (info.artist or "").strip(),
                "playing": status == _PLAYING,
                "is_player": _is_player(app),
                "_session": s,
            }
        )
    return out


def _pick(items: list[dict], app_hint: str = "") -> dict | None:
    """Выбирает сессию, в которую слать команду.

    Порядок важен и выведен из живой ситуации на машине фаундера: названное
    вслух приложение > играющий музыкальный плеер > играющее что угодно >
    музыкальный плеер на паузе > что угодно.
    """
    if not items:
        return None
    if app_hint:
        # Названо приложение — либо оно, либо ничего. Тихий откат на
        # «какую-нибудь другую сессию» стоил живого бага 25.08.2026: сразу
        # после переключения трека сессия Chrome на долю секунды пропадает
        # из списка, и «следующий трек» отчитывался голосовым сообщением из
        # Телеграма, которое никто не трогал.
        hint = app_hint.lower()
        named = [i for i in items if hint in i["app"].lower()]
        return named[0] if named else None

    rules = (
        lambda i: i["playing"] and i["is_player"],
        lambda i: i["playing"],
        lambda i: i["is_player"],
        lambda i: True,
    )
    for rule in rules:
        for item in items:
            if rule(item):
                return item
    return None


# Длина, после которой «артист» перестаёт быть именем. У фаундера в
# YouTube Music играют треки из Suno, и там в поле артиста лежит ВЕСЬ
# промпт генерации — 300+ символов «cinematic piano pop transformation
# anthem powerful emotional male vocals...». Озвучить это вслух значит
# читать простыню вместо ответа. Найдено живой проверкой 25.08.2026.
_ARTIST_LOOKS_LIKE_A_NAME = 60


def _describe(item: dict) -> str:
    """«Артист — Название» для ответа голосом, без пустых тире."""
    artist = item.get("artist") or ""
    if len(artist) > _ARTIST_LOOKS_LIKE_A_NAME:
        artist = ""
    parts = [p for p in (artist, item.get("title")) if p]
    return " — ".join(parts) if parts else (item.get("app") or "неизвестно")


async def now_playing() -> dict | None:
    """Что играет (или на чём остановились). None — сессий нет вовсе."""
    item = _pick(await sessions())
    if item is None:
        return None
    return {k: v for k, v in item.items() if k != "_session"}


async def control(action: str, app_hint: str = "") -> str:
    """Выполняет действие над плеером. Возвращает, что ответить человеку."""
    if action not in ACTIONS:
        raise ValueError(f"Неизвестное действие плеера: {action}")

    item = _pick(await sessions(), app_hint)

    if item is None:
        # WinRT молчит — либо его нет, либо ни одной сессии. Медиа-клавиша
        # хуже (не знает, куда попадёт), но лучше, чем «не могу».
        if _media_key(action):
            return _KEY_REPLY[action]
        raise NoPlayer(
            "Сейчас ничего не играет. Скажите «включи музыку» — открою YouTube Music."
        )

    session = item["_session"]
    try:
        if action == "toggle":
            ok = await session.try_toggle_play_pause_async()
            if not ok:
                return _fail(item)
            return "Пауза." if item["playing"] else f"Играет: {_describe(item)}."
        if action == "play":
            ok = await session.try_play_async()
            return f"Играет: {_describe(item)}." if ok else _fail(item)
        if action == "pause":
            ok = await session.try_pause_async()
            return "Пауза." if ok else _fail(item)
        if action == "stop":
            ok = await session.try_stop_async()
            return "Остановил." if ok else _fail(item)
        if action == "next":
            return await _after_skip(await session.try_skip_next_async(), item, "Следующий трек")
        if action == "previous":
            return await _after_skip(
                await session.try_skip_previous_async(), item, "Предыдущий трек"
            )
    except Exception as e:
        logger.exception("Команда плееру не прошла")
        return f"Не получилось управлять плеером: {e}"
    return _fail(item)


async def _after_skip(ok: bool, item: dict, label: str) -> str:
    """Название нового трека приходит не мгновенно — плеер сначала должен
    его загрузить, а его сессия на это время вообще пропадает из списка.
    Ждём короткими шагами: успели — ответ содержательный («Следующий трек:
    X»), не успели — просто «Следующий трек», и это тоже правда."""
    if not ok:
        return _fail(item)
    for _ in range(6):
        await asyncio.sleep(0.25)
        fresh = _pick(await sessions(), item["app"])
        if fresh and _describe(fresh) != _describe(item):
            return f"{label}: {_describe(fresh)}."
    return f"{label}."


def _fail(item: dict) -> str:
    return (
        f"{item['app']} не принял команду — возможно, вкладка закрыта "
        f"или плеер не отдаёт управление."
    )


# === Запасной путь: медиа-клавиши ==========================================

_KEYS = {
    "play": "playpause",
    "pause": "playpause",
    "toggle": "playpause",
    "next": "nexttrack",
    "previous": "prevtrack",
    "stop": "stop",
}

_KEY_REPLY = {
    "play": "Включаю.",
    "pause": "Пауза.",
    "toggle": "Переключил.",
    "next": "Следующий трек.",
    "previous": "Предыдущий трек.",
    "stop": "Остановил.",
}


def _media_key(action: str) -> bool:
    """Нажимает медиа-клавишу. True — нажали, False — не смогли."""
    key = _KEYS.get(action)
    if not key:
        return False
    try:
        import pyautogui

        pyautogui.press(key)
        return True
    except Exception as e:
        logger.warning("Медиа-клавиша %s не нажалась: %s", key, e)
        return False


# === Громкость =============================================================
#
# Отдельно от плеера: это громкость всей системы, а не одного приложения.
# Через IAudioEndpointVolume, а не через клавиши — клавиша умеет только «на
# шаг», а «поставь громкость сорок» просит уровень.


def _endpoint():
    from pycaw.utils import AudioUtilities

    return AudioUtilities.GetSpeakers().EndpointVolume


def get_volume() -> dict:
    v = _endpoint()
    return {"level": round(v.GetMasterVolumeLevelScalar() * 100), "muted": bool(v.GetMute())}


def set_volume(percent: int) -> str:
    level = max(0, min(100, int(percent)))
    v = _endpoint()
    v.SetMasterVolumeLevelScalar(level / 100, None)
    # Ставить уровень при включённом «без звука» — обещать звук, которого не
    # будет: человек услышит тишину и решит, что команда не сработала.
    if level > 0 and v.GetMute():
        v.SetMute(0, None)
    return f"Громкость {level}%."


def nudge_volume(delta: int) -> str:
    """«Громче»/«тише» — шагом, а не до уровня."""
    return set_volume(get_volume()["level"] + delta)


def set_mute(muted: bool) -> str:
    _endpoint().SetMute(1 if muted else 0, None)
    return "Звук выключен." if muted else "Звук включён."
