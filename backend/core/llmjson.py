"""Разбор JSON, пришедшего от языковой модели.

Модель просят ответить чистым JSON, а она отвечает как умеет: оборачивает
в ```json, добавляет «Конечно! Вот результат:», прячет массив под ключом,
который придумала на ходу, а единственный элемент отдаёт голым объектом
вместо массива из одного. Ни один из этих случаев не ошибка модели в её
понимании — это просто то, как она себя ведёт.

Раньше каждый вызывающий разбирал ответ сам и знал только те капризы, на
которых обжёгся лично: dream_cadence снимал ```-обрамление, но падал на
обёртках; content_factory знал ключ "items", но не знал про обрамление;
agent_engine не знал ни того, ни другого. Один и тот же баг находили по
три раза в разных местах (24.08.2026 — три подряд в Исследователе).

Здесь собрано всё сразу: новый вызывающий получает знание бесплатно.
Разбор поднимает ошибку, а не возвращает пустоту — молчаливый пустой
результат неотличим от «модели нечего сказать». Кому нужна мягкость, тот
берёт object_or/list_or и решает это осознанно.
"""
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Сколько символов ответа показываем в ошибке. Без образца в логе видно
# только «не JSON», и непонятно, что именно прислала модель; весь ответ
# писать тоже нельзя — он бывает на тысячи символов.
SAMPLE_CHARS = 200

_FENCE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)


class LLMJsonError(ValueError):
    """Ответ модели не удалось разобрать. Текст годится для показа человеку."""


def _sample(raw: str) -> str:
    text = " ".join(str(raw).split())
    return text[:SAMPLE_CHARS] + ("…" if len(text) > SAMPLE_CHARS else "")


def _strip_wrapping(raw: str) -> str:
    """Снимает ```-обрамление и болтовню вокруг JSON.

    Скобки ищем и фигурные, и квадратные: обрезка только по фигурным
    теряла массив, обёрнутый в текст, — а массив модель отдаёт не реже.
    """
    text = str(raw).strip()

    fence = _FENCE.search(text)
    if fence:
        return fence.group(1).strip()

    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    ends = [i for i in (text.rfind("}"), text.rfind("]")) if i != -1]
    if starts and ends:
        start, end = min(starts), max(ends)
        if end > start:
            return text[start : end + 1]
    return text


def loads(raw: str) -> Any:
    """Достаёт любое значение JSON из ответа модели."""
    if not raw or not str(raw).strip():
        raise LLMJsonError("Модель вернула пустой ответ")

    text = _strip_wrapping(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMJsonError(f"Модель вернула не JSON ({e}): {_sample(raw)}") from e


def parse_object(raw: str) -> dict:
    """Ответ, от которого ждём объект."""
    data = loads(raw)
    if not isinstance(data, dict):
        raise LLMJsonError(f"Ожидался объект, пришло {type(data).__name__}: {_sample(raw)}")
    return data


def parse_list(raw: str, item_hint: str | None = None) -> list:
    """Ответ, от которого ждём список.

    item_hint — имя поля, по которому узнаётся одиночный элемент, отданный
    без массива вокруг («topic» у Исследователя, «script» у контент-завода).
    Без подсказки одиночный объект не угадываем: иначе {"error": "..."}
    молча стал бы одной «валидной» записью.
    """
    data = loads(raw)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        if item_hint and item_hint in data:
            return [data]

        # Ключ обёртки модель выбирает сама и каждый раз новый: items,
        # topics, «результаты»… Смысла в ярлыке нет — берём первый список.
        for value in data.values():
            if isinstance(value, list):
                return value

        if not data:
            return []  # пустой объект — законное «нечего предложить»

    raise LLMJsonError(f"Ожидался список, пришло: {_sample(raw)}")


def object_or(default: dict, raw: str) -> dict:
    """Разбор без падения — для фоновых работ, которым важнее продолжить.

    Пишем в лог: тихая подмена на пустоту не должна выглядеть как «модель
    ничего не нашла».
    """
    try:
        return parse_object(raw)
    except LLMJsonError as e:
        logger.warning("Ответ модели не разобран, беру значение по умолчанию: %s", e)
        return default


def list_or(default: list, raw: str, item_hint: str | None = None) -> list:
    try:
        return parse_list(raw, item_hint=item_hint)
    except LLMJsonError as e:
        logger.warning("Ответ модели не разобран, беру значение по умолчанию: %s", e)
        return default
