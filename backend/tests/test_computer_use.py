"""Компьютерное управление — клик, ввод текста, защита от необратимого.

pyautogui/pyperclip везде подменены: тест, который реально двигает мышь и
кликает по машине, где сам крутится — не тест, а сюрприз. Проверяем
логику (что заблокировано, что дошло до вызова, куда реально указывает
клик), не настоящий ввод.
"""
import pytest

from backend.services import computer_use as cu
from backend.services import pending_action
from backend.services import tools as tools_svc


@pytest.fixture(autouse=True)
def clean_pending_actions():
    pending_action._store.clear()
    yield
    pending_action._store.clear()


@pytest.fixture
def with_gemini_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


@pytest.fixture
def without_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.fixture
def fixed_screen_size(monkeypatch):
    """1920x1080 — реальный частый монитор, шире MAX_SCREENSHOT_DIM (1280),
    поэтому масштабирование реально включается в тесте, не остаётся 1.0
    случайно."""
    monkeypatch.setattr(cu.pyautogui, "size", lambda: (1920, 1080))


# --- Защита по подписи (_guard) ---


@pytest.mark.parametrize(
    "label",
    [
        "Оплатить сейчас",
        "buy now",
        "Отправить письмо",
        "Удалить аккаунт",
        "send SMS",
        "Confirm purchase",
        "Купить билет",
        "Перевод денег другу",
        # Найдено код-ревью 19.08.2026 — первая версия фильтра пропускала
        # именно эти реальные банковские/магазинные формулировки:
        "Перевести",
        "Перевести на карту",
        "Переведи 500 рублей другу",
        "Заказать",
        "Оформить заказ",
        "Снять наличные",
        "Списать со счёта",
        "Списание",
        "Отправляй",
    ],
)
def test_risky_labels_are_blocked(label):
    with pytest.raises(cu.ActionBlocked):
        cu._guard(label)


@pytest.mark.parametrize(
    "label",
    [
        "Главная страница",
        "Поиск",
        "Следующая статья",
        "Меню Файл",
        "Второй мозг",
        "",
        "Снять скриншот",  # «снять» само по себе — не платёж
        "Снять видео",
    ],
)
def test_safe_labels_pass_through(label):
    cu._guard(label)  # не должно бросить


# --- Масштаб координат (найдено код-ревью 19.08.2026) ---


def test_scale_factor_is_1_on_small_screen(monkeypatch):
    """Экран меньше MAX_SCREENSHOT_DIM — скриншот не уменьшался, масштаб не нужен."""
    monkeypatch.setattr(cu.pyautogui, "size", lambda: (1024, 768))
    assert cu.scale_factor() == 1.0


def test_scale_factor_matches_real_downscale(fixed_screen_size):
    """1920 -> 1280 по большей стороне: коэффициент должен вернуть 1920 обратно."""
    factor = cu.scale_factor()
    assert factor == pytest.approx(1920 / 1280)


def test_click_rescales_model_coordinates_to_real_screen(fixed_screen_size, monkeypatch):
    """Самая критичная проверка: координата с уменьшенного скриншота модели
    должна попасть в правильную точку настоящего экрана, а не остаться как есть."""
    calls = []
    monkeypatch.setattr(cu.pyautogui, "click", lambda x, y: calls.append((x, y)))

    # Модель вернула координату на картинке 1280px, реальный экран — 1920px
    cu.click(640, 360, "Второй мозг")

    real_x, real_y = calls[0]
    assert real_x == round(640 * 1920 / 1280)
    assert real_y == round(360 * 1920 / 1280)


def test_click_calls_pyautogui_for_safe_label(monkeypatch):
    monkeypatch.setattr(cu.pyautogui, "size", lambda: (100, 100))  # меньше MAX_SCREENSHOT_DIM — фактор 1.0
    calls = []
    monkeypatch.setattr(cu.pyautogui, "click", lambda x, y: calls.append((x, y)))

    result = cu.click(50, 60, "Второй мозг")

    assert calls == [(50, 60)]
    assert "50" in result and "60" in result


def test_click_blocks_risky_label_without_calling_pyautogui(monkeypatch):
    calls = []
    monkeypatch.setattr(cu.pyautogui, "click", lambda x, y: calls.append((x, y)))

    with pytest.raises(cu.ActionBlocked):
        cu.click(100, 200, "Оплатить")

    assert calls == []  # клик реально не произошёл


def test_type_text_uses_clipboard_not_typewrite(monkeypatch):
    """Кириллица через typewrite() у pyautogui не работает — должен быть буфер обмена."""
    copied = []
    hotkeys = []
    monkeypatch.setattr(cu.pyperclip, "copy", lambda text: copied.append(text))
    monkeypatch.setattr(cu.pyautogui, "hotkey", lambda *keys: hotkeys.append(keys))

    cu.type_text("привет, это тест", "поле поиска")

    assert copied == ["привет, это тест"]
    assert hotkeys == [("ctrl", "v")]


def test_type_text_blocks_on_risky_content_even_with_safe_label(monkeypatch):
    """Подпись поля безобидная, но сам текст выдаёт платёж — тоже блокируется."""
    copied = []
    monkeypatch.setattr(cu.pyperclip, "copy", lambda text: copied.append(text))
    monkeypatch.setattr(cu.pyautogui, "hotkey", lambda *keys: None)

    with pytest.raises(cu.ActionBlocked):
        cu.type_text("оплатить 5000 рублей", label="произвольное поле")

    assert copied == []


# --- Обёртки для tool-calling (run_screen_*) ---


@pytest.mark.asyncio
async def test_run_screen_click_reports_block_as_text_not_exception(monkeypatch):
    """Модель получает текст об отказе, а не падение всего цикла инструментов."""
    monkeypatch.setattr(cu.pyautogui, "click", lambda x, y: (_ for _ in ()).throw(AssertionError("не должен был кликнуть")))

    result = await cu.run_screen_click({"x": 10, "y": 20, "label": "Оплатить заказ"})

    assert "⛔" in result


@pytest.mark.asyncio
async def test_run_screen_click_executes_safe_click(monkeypatch):
    monkeypatch.setattr(cu.pyautogui, "size", lambda: (100, 100))
    calls = []
    monkeypatch.setattr(cu.pyautogui, "click", lambda x, y: calls.append((x, y)))

    result = await cu.run_screen_click({"x": 42, "y": 43, "label": "Ссылка на статью"})

    assert calls == [(42, 43)]
    assert "42" in result


# --- Заблокированное действие уходит в pending_action.py (19.08.2026, шаг подтверждения) ---


@pytest.mark.asyncio
async def test_blocked_click_is_stored_as_pending_action(monkeypatch):
    monkeypatch.setattr(cu.pyautogui, "size", lambda: (100, 100))
    monkeypatch.setattr(cu.pyautogui, "click", lambda x, y: (_ for _ in ()).throw(AssertionError))

    await cu.run_screen_click({"x": 10, "y": 20, "label": "Оплатить заказ"}, action_key="telegram:42")

    action = pending_action.get("telegram:42")
    assert action is not None
    assert action.kind == "click"
    assert action.payload == {"x": 10, "y": 20, "label": "Оплатить заказ"}


@pytest.mark.asyncio
async def test_blocked_type_is_stored_as_pending_action(monkeypatch):
    monkeypatch.setattr(cu.pyperclip, "copy", lambda text: None)
    monkeypatch.setattr(cu.pyautogui, "hotkey", lambda *k: None)

    await cu.run_screen_type({"text": "оплатить 500", "label": ""}, action_key="telegram:42")

    action = pending_action.get("telegram:42")
    assert action is not None
    assert action.kind == "type"
    assert action.payload == {"text": "оплатить 500", "label": ""}


@pytest.mark.asyncio
async def test_safe_click_does_not_touch_pending_action(monkeypatch):
    monkeypatch.setattr(cu.pyautogui, "size", lambda: (100, 100))
    monkeypatch.setattr(cu.pyautogui, "click", lambda x, y: None)

    await cu.run_screen_click({"x": 5, "y": 6, "label": "Меню"}, action_key="telegram:42")

    assert pending_action.get("telegram:42") is None


def test_click_confirmed_skips_guard_and_rescales(monkeypatch):
    """Подтверждённое действие обязано пройти, даже если подпись — прямой платёж:
    риск уже проверен человеком, не текстом от модели."""
    monkeypatch.setattr(cu.pyautogui, "size", lambda: (1920, 1080))
    calls = []
    monkeypatch.setattr(cu.pyautogui, "click", lambda x, y: calls.append((x, y)))

    result = cu.click_confirmed(640, 360, "Оплатить заказ")

    real_x, real_y = calls[0]
    assert real_x == round(640 * 1920 / 1280)
    assert real_y == round(360 * 1920 / 1280)
    assert "Оплатить заказ" in result


def test_type_text_confirmed_skips_guard(monkeypatch):
    copied = []
    monkeypatch.setattr(cu.pyperclip, "copy", lambda text: copied.append(text))
    monkeypatch.setattr(cu.pyautogui, "hotkey", lambda *k: None)

    result = cu.type_text_confirmed("оплатить 5000 рублей", "поле суммы")

    assert copied == ["оплатить 5000 рублей"]
    assert "поле суммы" in result


# --- Кому доступны инструменты экрана ---


def test_orpheus_has_screen_tools(with_gemini_key):
    names = [t["function"]["name"] for t in tools_svc.tools_for("Orpheus")]
    assert "screen_click" in names
    assert "screen_look" in names


def test_orpheus_has_no_screen_tools_without_gemini_key(without_gemini_key):
    """Найдено код-ревью 19.08.2026: без ключа screen_look гарантированно
    откажет — инструмент не должен вообще предлагаться, как и web_search
    без своего ключа."""
    names = [t["function"]["name"] for t in tools_svc.tools_for("Orpheus")]
    assert "screen_click" not in names
    assert "screen_look" not in names


def test_other_personas_do_not_have_screen_tools(with_gemini_key):
    for persona in ("Architect", "Sekhmet", "Philosopher"):
        names = [t["function"]["name"] for t in tools_svc.tools_for(persona)]
        assert "screen_click" not in names


def test_vision_configured_follows_the_env_key(with_gemini_key):
    assert cu.vision_configured()


# --- system_status: Ра смотрит в свой же конфиг, а не спрашивает фаундера ---


def test_orpheus_has_system_status_tool():
    """Не завязан на ключи — в отличие от screen_look/web_search, читает
    только .env этой же машины, ничего внешнего не требует."""
    names = [t["function"]["name"] for t in tools_svc.tools_for("Orpheus")]
    assert "system_status" in names


def test_other_personas_do_not_have_system_status_tool():
    for persona in ("Architect", "Sekhmet", "Philosopher"):
        names = [t["function"]["name"] for t in tools_svc.tools_for(persona)]
        assert "system_status" not in names


@pytest.mark.asyncio
async def test_system_status_reports_tts_and_wakeword(monkeypatch):
    monkeypatch.setenv("NEXUS_TTS_ENGINE", "edge")
    monkeypatch.setenv("NEXUS_TTS_VOICE", "ru-RU-DmitryNeural")
    result = await tools_svc.run_system_status({}, "")
    assert "edge" in result
    assert "ru-RU-DmitryNeural" in result
    assert "8422" in result


def test_vision_not_configured_without_key(without_gemini_key):
    assert not cu.vision_configured()
