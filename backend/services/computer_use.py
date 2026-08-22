"""Компьютерное управление — экран, клик, ввод текста (шаг 3, 19.08.2026).

Самая крупная и самая рискованная часть плана 19.08.2026: Джарвис смотрит
на экран и управляет мышью/клавиатурой. Фаундер прямо разрешил делать
автономно: кликать по сайтам, переходить, смотреть, искать информацию.
Оплаты, отправку SMS/писем и подобное необратимое — сначала подтвердить
словами, не молча.

Два слоя защиты, не один — прямая цитата фаундера про подтверждение
переведена в код, а не оставлена только в промпте модели:
1. Инструменту в описании прямо сказано не жать такие кнопки самому.
2. Здесь, в коде — жёсткая проверка по словам в подписи (label), которую
   модель обязана передать вместе с координатами/текстом. Если в подписи
   или в самом вводимом тексте есть слово из списка ниже («оплат»,
   «отправ», «удалит», pay/send/delete и т.д.) — действие НЕ выполняется,
   что бы модель ни решила. Промпт можно обмануть или ослышаться при
   голосовой команде, эту проверку — нет: она смотрит на факт (подпись
   кнопки), а не на намерение модели.

Настоящее подтверждение фаундером (следующий раунд, 19.08.2026 вечер):
заблокированный клик/ввод кладётся в pending_action.py вместе с исходными
координатами/текстом; повторное явное «подтверждаю» разбирается в
conversation.py._try_confirm тем же приёмом, что «открой X» и «создай
задачу», и исполняет действие напрямую через click_confirmed()/
type_text_confirmed() — в обход модели и в обход _guard (риск уже проверен
человеком, а не текстом от модели).
"""
import asyncio
import io
import logging
import os
import re
from typing import Any

import pyautogui
import pyperclip
from PIL import Image

logger = logging.getLogger(__name__)

# В угол экрана мышью — аварийный стоп pyautogui (встроенный механизм библиотеки)
pyautogui.FAILSAFE = True
# Пауза между действиями — не долбить систему кликами быстрее, чем она успевает реагировать
pyautogui.PAUSE = 0.15

# Сторона, до которой уменьшается скриншот для модели — одно число на
# take_screenshot/scale_factor/run_screen_look, не три зашитых копии
MAX_SCREENSHOT_DIM = 1280

# Найдено код-ревью 19.08.2026, дважды подряд — сначала пропускало «Перевести»,
# «Заказать», «Оформить заказ», «Снять наличные», «Списать со счёта», потом,
# после первой правки, ещё и «Перевести» (без «на карту»), «Списать со счёта»,
# «Отправляй». Причина оба раза одна: русские глаголы меняют согласную между
# формами (списать/спишу — т/ш, оплатить/оплачу — т/ч, заказать/закажу —
# з/ж), и длинные точные окончания («спиш[иу]», «отправ(ь|ить|ка|ляю)»)
# ловят одни формы и пропускают другие. Здесь — короткие корни, ловящие
# слово ЦЕЛИКОМ ПОДСТРОКОЙ независимо от окончания, где только можно, и
# обе чередующиеся согласные там, где корень короче общего не бывает.
# Цена ложного срабатывания (лишний вопрос «точно?») несравнимо меньше
# цены пропуска настоящего платежа — специально широко, не только под
# формы, которые нашлись в этот раз.
_RISKY_LABEL = re.compile(
    r"оплат|оплач|"                           # оплатить/оплачу
    r"куп|"                                    # купить/куплю/покупка
    r"заплат|заплач|"                         # заплатить/заплачу
    r"перев|"                                  # перевести/переведи/перевод/перевёл — широкий корень нарочно
    r"спис|спиш|"                             # списать/списание — спишу/спиши
    r"снять\s*(наличн|деньги|со\s*сч)|"       # «снять» само по себе слишком общее (снять видео/скриншот)
    r"заказ|закаж|"                           # заказать/закажу
    r"оформ|"                                  # оформить/оформляю заказ
    r"отправ|"                                 # любая форма «отправ...»
    r"удал|снес|снест|подтверд.*(плат|перев)|"
    r"\bpay\b|\bbuy\b|\bpurchase\b|\bsend\b|\bdelete\b|\bremove\b|"
    r"\btransfer\b|\bcheckout\b|\bconfirm\b|\border\b|\bwithdraw\b",
    re.IGNORECASE,
)


class ActionBlocked(RuntimeError):
    """Действие похоже на необратимое — не выполнено, нужно подтверждение человека."""


def _guard(*texts: str) -> None:
    for text in texts:
        if text and _RISKY_LABEL.search(text):
            raise ActionBlocked(
                f"«{text}» похоже на оплату/отправку/удаление — не делаю сам. "
                f"Спроси у фаундера прямо и жди явного «подтверждаю»."
            )


def scale_factor(max_dim: int = MAX_SCREENSHOT_DIM) -> float:
    """Во сколько раз уменьшен скриншот (см. take_screenshot).

    Найдено код-ревью 19.08.2026 — критично: скриншот уменьшался до
    max_dim по большей стороне для модели, а click()/type_text() били по
    настоящим координатам экрана без пересчёта — на любом мониторе шире
    1280px КАЖДЫЙ клик бил не туда. PIL Image.thumbnail() масштабирует по
    min(max_w/w, max_h/h); при max_w == max_h == max_dim это ровно
    max_dim / max(ширина, высота) — здесь возвращаем обратный коэффициент,
    чтобы перевести координаты с уменьшенной картинки обратно в реальные
    пиксели экрана. Считается заново от pyautogui.size(), не хранится
    отдельным состоянием — так click() и screen_look независимо приходят
    к одному числу, не рискуя разойтись.
    """
    width, height = pyautogui.size()
    longest = max(width, height)
    return longest / max_dim if longest > max_dim else 1.0


def take_screenshot(max_dim: int = MAX_SCREENSHOT_DIM) -> bytes:
    """PNG-скриншот экрана, уменьшенный — незачем гонять мегабайты в модель."""
    img = pyautogui.screenshot()
    img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _do_click(x: int, y: int) -> tuple[int, int]:
    """Настоящий клик без проверки _guard — общий код для click() и
    click_confirmed(), риск проверяется только на входе в каждую из них."""
    factor = scale_factor()
    real_x, real_y = round(x * factor), round(y * factor)
    pyautogui.click(real_x, real_y)
    return real_x, real_y


def _do_type(text: str) -> None:
    """Настоящий ввод через буфер обмена — общий код для type_text() и
    type_text_confirmed(). pyautogui.typewrite() симулирует нажатия клавиш
    американской раскладки и не умеет кириллицу — русский текст пришёл бы
    битым, через буфер обмена + Ctrl+V работает для любого языка."""
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")


def click(x: int, y: int, label: str = "") -> str:
    """x, y — координаты на уменьшенном скриншоте (см. take_screenshot/screen_look),
    не на настоящем экране; здесь пересчитываются в реальные пиксели."""
    _guard(label)
    real_x, real_y = _do_click(x, y)
    return f"Кликнул в ({real_x}, {real_y})" + (f" — «{label}»" if label else "")


def type_text(text: str, label: str = "") -> str:
    """Вставляет текст через буфер обмена, не typewrite() — см. _do_type."""
    _guard(label, text)
    _do_type(text)
    return f"Ввёл текст ({len(text)} симв.)"


def click_confirmed(x: int, y: int, label: str = "") -> str:
    """Клик БЕЗ проверки _guard — только для действия, уже подтверждённого
    фаундером через pending_action.py («подтверждаю» в conversation.py).
    Не регистрировать как инструмент модели: модель обязана проходить
    только через click()/screen_click, где риск проверяется на входе."""
    real_x, real_y = _do_click(x, y)
    return f"Кликнул в ({real_x}, {real_y})" + (f" — «{label}»" if label else "")


def type_text_confirmed(text: str, label: str = "") -> str:
    """Ввод БЕЗ проверки _guard — та же оговорка, что у click_confirmed."""
    _do_type(text)
    return f"Ввёл текст ({len(text)} симв.)" + (f" — «{label}»" if label else "")


def press_key(key: str) -> str:
    pyautogui.press(key)
    return f"Нажал {key}"


def scroll(amount: int) -> str:
    pyautogui.scroll(amount)
    return f"Прокрутил на {amount}"


def vision_configured() -> bool:
    """screen_look зовёт Gemini — без ключа он гарантированно откажет.

    Найдено код-ревью 19.08.2026: у web_search есть такая же проверка
    (websearch.is_configured()) перед тем, как предложить инструмент
    модели, а у экранных инструментов её не было — модель без ключа всё
    равно получала screen_look и тратила ход на заведомый провал.
    """
    return bool(os.getenv("GEMINI_API_KEY", ""))


# --- Инструменты для модели (реестр в tools.py) ---
#
# screen_look смотрит через Gemini (описание в llm.py) — отдельный клиент,
# не персона в разговоре: у Gemini нет tool-calling, а у deepseek (на нём
# сидят персоны) нет зрения. Поэтому Gemini смотрит и описывает словами,
# а решает и жмёт та же модель, что ведёт разговор.

SCREEN_LOOK_SPEC: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "screen_look",
        "description": (
            "Смотрит на текущий экран компьютера фаундера и описывает, что на "
            "нём есть — с примерными координатами (x, y) кнопок, полей и ссылок. "
            "Зови перед любым screen_click/screen_type, чтобы не гадать координаты: "
            "спросить у экрана дешевле, чем промахнуться."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Что именно ищешь на экране, например «где кнопка входа»",
                },
            },
            "required": ["question"],
        },
    },
}

SCREEN_CLICK_SPEC: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "screen_click",
        "description": (
            "Кликает мышью в точке экрана. Координаты бери из недавнего "
            "screen_look, не выдумывай. НЕ зови для оплаты, отправки денег, "
            "SMS, писем, удаления или другого необратимого — вместо этого "
            "спроси у фаундера словами и жди явного «подтверждаю». Система "
            "всё равно откажет в таком клике на уровне кода, даже если позвать."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "Координата X в пикселях экрана"},
                "y": {"type": "integer", "description": "Координата Y в пикселях экрана"},
                "label": {
                    "type": "string",
                    "description": "Подпись того, на что кликаешь (текст кнопки/ссылки) — обязательно, для проверки безопасности",
                },
            },
            "required": ["x", "y", "label"],
        },
    },
}

SCREEN_TYPE_SPEC: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "screen_type",
        "description": (
            "Печатает текст туда, где сейчас курсор ввода (сначала кликни полем "
            "через screen_click). НЕ вводи номера карт, коды подтверждения "
            "платежей и подобное без явного «подтверждаю» от фаундера."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Что напечатать"},
                "label": {
                    "type": "string",
                    "description": "Что это за поле (например «поле поиска», «имя пользователя»)",
                    "default": "",
                },
            },
            "required": ["text"],
        },
    },
}

SCREEN_KEY_SPEC: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "screen_key",
        "description": "Нажимает одну клавишу — enter, tab, escape, backspace и подобные.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Название клавиши, например 'enter'"},
            },
            "required": ["key"],
        },
    },
}

SCREEN_SCROLL_SPEC: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "screen_scroll",
        "description": "Прокручивает страницу/окно под курсором.",
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "integer",
                    "description": "Положительное — вверх, отрицательное — вниз",
                },
            },
            "required": ["amount"],
        },
    },
}


async def run_screen_look(arguments: dict[str, Any], action_key: str = "") -> str:
    from .llm import LLMService, TranscriptionUnavailable

    question = str(arguments.get("question") or "Опиши, что на экране, с координатами ключевых элементов")
    try:
        image = await asyncio.to_thread(take_screenshot)
        llm = LLMService()
        prompt = (
            f"Это скриншот экрана компьютера (уменьшен до {MAX_SCREENSHOT_DIM}px по большей стороне). "
            f"{question}\n\nДля каждого найденного элемента дай примерные координаты x,y "
            f"в пикселях ОТНОСИТЕЛЬНО ЭТОГО УМЕНЬШЕННОГО ИЗОБРАЖЕНИЯ, кратко, списком."
        )
        return await llm.describe_screen(image, prompt)
    except TranscriptionUnavailable as e:
        return str(e)
    except Exception as e:
        logger.exception("screen_look не удался")
        return f"Не получилось посмотреть на экран: {e}"


async def run_screen_click(arguments: dict[str, Any], action_key: str = "") -> str:
    try:
        x = int(arguments.get("x", 0))
        y = int(arguments.get("y", 0))
        label = str(arguments.get("label") or "")
        return await asyncio.to_thread(click, x, y, label)
    except ActionBlocked as e:
        from . import pending_action

        pending_action.hold(action_key, "click", {"x": x, "y": y, "label": label}, str(e))
        return f"⛔ {e}"
    except Exception as e:
        logger.exception("screen_click не удался")
        return f"Клик не удался: {e}"


async def run_screen_type(arguments: dict[str, Any], action_key: str = "") -> str:
    try:
        text = str(arguments.get("text") or "")
        label = str(arguments.get("label") or "")
        return await asyncio.to_thread(type_text, text, label)
    except ActionBlocked as e:
        from . import pending_action

        pending_action.hold(action_key, "type", {"text": text, "label": label}, str(e))
        return f"⛔ {e}"
    except Exception as e:
        logger.exception("screen_type не удался")
        return f"Ввод текста не удался: {e}"


async def run_screen_key(arguments: dict[str, Any], action_key: str = "") -> str:
    try:
        return await asyncio.to_thread(press_key, str(arguments.get("key") or ""))
    except Exception as e:
        logger.exception("screen_key не удался")
        return f"Нажатие клавиши не удалось: {e}"


async def run_screen_scroll(arguments: dict[str, Any], action_key: str = "") -> str:
    try:
        return await asyncio.to_thread(scroll, int(arguments.get("amount", 0)))
    except Exception as e:
        logger.exception("screen_scroll не удался")
        return f"Прокрутка не удалась: {e}"
