"""Разбор голосовых команд компьютеру.

Ни один тест не трогает настоящую машину: плеер, громкость и окна
подменяются. Живая проверка на реальном YouTube Music/Chrome делалась
отдельно (25.08.2026) — тесты стерегут разбор речи, а не Windows.

Главное, что здесь проверяется, — не «команда сработала», а границы:
обычная фраза («привет», «открой хром», «создай задачу») НЕ должна
попасть в команды компьютеру, иначе она перестанет доходить до модели.
"""
import pytest

from backend.services import pc_commands


@pytest.fixture
def player(monkeypatch):
    """Подменяет плеер: тесты не должны включать музыку на машине."""
    calls: list[str] = []

    async def control(action: str, app_hint: str = "") -> str:
        calls.append(action)
        return f"ok:{action}"

    async def now_playing():
        return {"app": "Chrome", "title": "Песня", "artist": "", "playing": False, "is_player": True}

    monkeypatch.setattr(pc_commands.media_control, "control", control)
    monkeypatch.setattr(pc_commands.media_control, "now_playing", now_playing)
    return calls


@pytest.fixture
def silent_player(monkeypatch):
    """Плеера на машине нет вовсе."""

    async def now_playing():
        return None

    monkeypatch.setattr(pc_commands.media_control, "now_playing", now_playing)


@pytest.mark.parametrize(
    "phrase,action",
    [
        ("пауза", "pause"),
        ("паузу", "pause"),
        ("поставь на паузу", "pause"),
        ("продолжи", "play"),
        ("играй дальше", "play"),
        ("следующий трек", "next"),
        ("включи следующую песню", "next"),
        ("переключи трек", None),  # без «следующий» это не команда плееру
        ("предыдущий трек", "previous"),
        ("останови музыку", "pause"),
        ("выключи музыку", "pause"),
    ],
)
@pytest.mark.asyncio
async def test_player_phrases(player, phrase, action):
    reply = await pc_commands.try_command(phrase)
    if action is None:
        assert reply is None
        return
    assert player == [action], f"«{phrase}» ушло не туда"
    assert reply == f"ok:{action}"


@pytest.mark.asyncio
async def test_bare_stop_is_not_a_player_command(player):
    """«Стоп» затыкает саму речь Джарвиса (перебивание, 23.08.2026).
    Отдать это слово плееру значит сломать уже работающее."""
    assert await pc_commands.try_command("стоп") is None
    assert player == []


@pytest.mark.asyncio
async def test_play_music_resumes_open_player(player):
    """Плеер уже открыт и на паузе — «включи музыку» значит «продолжи»."""
    assert await pc_commands.try_command("включи музыку") == "ok:play"


@pytest.mark.asyncio
async def test_play_music_falls_through_when_nothing_is_open(silent_player):
    """Плеера нет — молчим, и system_open откроет YouTube Music, как раньше."""
    assert await pc_commands.try_command("включи музыку") is None


@pytest.mark.asyncio
async def test_whats_playing_says_paused(player):
    reply = await pc_commands.try_command("что играет")
    assert "На паузе" in reply and "Песня" in reply


# === Громкость =============================================================


@pytest.fixture
def volume(monkeypatch):
    state = {"level": 50, "muted": False}

    def get_volume():
        return dict(state)

    def set_volume(percent):
        state["level"] = max(0, min(100, int(percent)))
        return f"Громкость {state['level']}%."

    def set_mute(muted):
        state["muted"] = muted
        return "Звук выключен." if muted else "Звук включён."

    monkeypatch.setattr(pc_commands.media_control, "get_volume", get_volume)
    monkeypatch.setattr(pc_commands.media_control, "set_volume", set_volume)
    monkeypatch.setattr(pc_commands.media_control, "set_mute", set_mute)
    monkeypatch.setattr(
        pc_commands.media_control,
        "nudge_volume",
        lambda delta: set_volume(state["level"] + delta),
    )
    return state


@pytest.mark.asyncio
async def test_volume_level(volume):
    await pc_commands.try_command("поставь громкость 30")
    assert volume["level"] == 30


@pytest.mark.asyncio
async def test_volume_steps(volume):
    await pc_commands.try_command("громче")
    assert volume["level"] == 60
    await pc_commands.try_command("тише")
    assert volume["level"] == 50


@pytest.mark.asyncio
async def test_mute_and_unmute(volume):
    await pc_commands.try_command("выключи звук")
    assert volume["muted"] is True
    await pc_commands.try_command("включи звук")
    assert volume["muted"] is False


@pytest.mark.asyncio
async def test_volume_over_hundred_is_clamped(volume):
    await pc_commands.try_command("громкость 300")
    assert volume["level"] == 100


# === Окна, папки, буфер ====================================================


@pytest.fixture
def desktop(monkeypatch):
    calls: dict[str, list] = {"closed": [], "focused": [], "folders": []}
    open_titles = ["Nexus OS - Google Chrome", "bot.py - Visual Studio Code"]

    monkeypatch.setattr(pc_commands.system_control, "list_windows", lambda: list(open_titles))
    monkeypatch.setattr(
        pc_commands.system_control,
        "_match_windows",
        lambda name: [t for t in open_titles if _spoken(name) in t.lower()],
    )
    monkeypatch.setattr(
        pc_commands.system_control,
        "close_app",
        lambda name: calls["closed"].append(name) or "Закрыл.",
    )
    monkeypatch.setattr(
        pc_commands.system_control,
        "focus_app",
        lambda name: calls["focused"].append(name) or "Переключился.",
    )
    monkeypatch.setattr(
        pc_commands.system_control,
        "open_folder",
        lambda name: calls["folders"].append(name) or "Открываю.",
    )
    monkeypatch.setattr(pc_commands.system_control, "minimize_all", lambda: "Свернул всё.")
    monkeypatch.setattr(pc_commands.system_control, "clipboard_get", lambda: "текст в буфере")
    monkeypatch.setattr(
        pc_commands.system_control, "screenshot", lambda: "Снимок экрана: C:/Desktop/Экран.png"
    )
    return calls


def _spoken(name: str) -> str:
    from backend.services.system_open import SPOKEN_APP_NAMES

    q = name.strip().lower()
    return SPOKEN_APP_NAMES.get(q, q)


@pytest.mark.asyncio
async def test_close_app_by_russian_name(desktop):
    assert await pc_commands.try_command("закрой хром") == "Закрыл."
    assert desktop["closed"] == ["хром"]


@pytest.mark.asyncio
async def test_close_is_ignored_when_no_such_window(desktop):
    """«Закрой вопрос» — обычная фраза, а не команда окну. Такой команды
    нет — фраза обязана уйти в разговор с моделью, а не упереться в отказ."""
    assert await pc_commands.try_command("закрой вопрос по клиенту") is None
    assert desktop["closed"] == []


@pytest.mark.asyncio
async def test_open_folder(desktop):
    assert await pc_commands.try_command("открой папку загрузки") == "Открываю."
    assert desktop["folders"] == ["загрузки"]


@pytest.mark.asyncio
async def test_whats_open_lists_windows(desktop):
    reply = await pc_commands.try_command("что открыто")
    assert "Google Chrome" in reply


@pytest.mark.asyncio
async def test_clipboard_read(desktop):
    assert "текст в буфере" in await pc_commands.try_command("что в буфере")


@pytest.mark.asyncio
async def test_minimize_all(desktop):
    assert await pc_commands.try_command("сверни всё") == "Свернул всё."


@pytest.mark.parametrize("phrase", ["скриншот", "сделай скриншот", "сними снимок экрана"])
@pytest.mark.asyncio
async def test_screenshot(desktop, phrase):
    assert "Снимок экрана" in await pc_commands.try_command(phrase)


# === Питание ===============================================================


@pytest.mark.asyncio
async def test_power_never_runs_without_confirmation(monkeypatch):
    """Единственное необратимое из команд компьютеру. Оно обязано лечь в
    pending_action и ждать «подтверждаю», а не выполниться сразу."""
    from backend.services import pending_action

    monkeypatch.setattr(
        pc_commands.system_control,
        "power_confirmed",
        lambda action: pytest.fail("питание выполнилось без подтверждения"),
    )
    reply = await pc_commands.try_command("выключи компьютер", confirm_key="тест:1")
    assert "подтверждаю" in reply.lower()

    held = pending_action.get("тест:1")
    assert held.kind == "power"
    assert held.payload == {"action": "shutdown"}
    pending_action.clear("тест:1")


@pytest.mark.asyncio
async def test_power_is_not_offered_without_a_place_to_confirm():
    """Без ключа подтверждать негде — предлагать выключение нельзя."""
    assert await pc_commands.try_command("выключи компьютер") is None


@pytest.mark.parametrize(
    "phrase,action",
    [
        ("перезагрузи компьютер", "restart"),
        ("усыпи компьютер", "sleep"),
        ("выключи комп", "shutdown"),
    ],
)
@pytest.mark.asyncio
async def test_power_verbs(phrase, action):
    from backend.services import pending_action

    await pc_commands.try_command(phrase, confirm_key="тест:2")
    assert pending_action.get("тест:2").payload == {"action": action}
    pending_action.clear("тест:2")


# === Границы ===============================================================


@pytest.mark.parametrize(
    "phrase",
    [
        "привет, как дела",
        "открой хром",
        "создай задачу купить корм",
        "запиши идею сделать бота",
        "расскажи, что было вчера",
        "поставь встречу в четверг",
        "выключи свет на кухне",
    ],
)
@pytest.mark.asyncio
async def test_ordinary_speech_is_left_alone(phrase, player, volume, desktop):
    """Самое дорогое свойство модуля: не съедать чужие фразы. Каждая из
    этих строк принадлежит другому обработчику или модели."""
    assert await pc_commands.try_command(phrase, confirm_key="тест:3") is None
