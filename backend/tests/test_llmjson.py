"""Общий разбор JSON от языковой модели.

До этого каждый модуль разбирал ответ сам, и каждый знал только те
капризы модели, на которых успел обжечься лично: dream_cadence умел
снимать ```json-обрамление, но не знал про обёртки-ключи; content_factory
знал про ключ "items", но падал на ```json; agent_engine не умел ни того,
ни другого. Один и тот же баг ловился по три раза в разных местах.

Здесь собраны ВСЕ формы, которые модель выдавала вживую (24.08.2026 —
DeepSeek в json_mode), чтобы следующий вызывающий получил их бесплатно.
"""
import pytest

from backend.core import llmjson


# === Чистый JSON ===

def test_plain_object():
    assert llmjson.parse_object('{"a": 1}') == {"a": 1}


def test_plain_list():
    assert llmjson.parse_list('[{"a": 1}]') == [{"a": 1}]


# === ```json-обрамление ===

def test_object_in_json_fence():
    raw = '```json\n{"a": 1}\n```'
    assert llmjson.parse_object(raw) == {"a": 1}


def test_object_in_bare_fence():
    assert llmjson.parse_object('```\n{"a": 1}\n```') == {"a": 1}


def test_list_in_fence():
    """Обрамление снимали только для объектов — массивы падали."""
    assert llmjson.parse_list('```json\n[{"a": 1}]\n```') == [{"a": 1}]


# === Болтовня вокруг ===

def test_object_with_prose_around():
    raw = 'Конечно! Вот результат:\n{"a": 1}\nНадеюсь, помог.'
    assert llmjson.parse_object(raw) == {"a": 1}


def test_list_with_prose_around():
    """Обрезка искала только фигурные скобки — массив в болтовне терялся."""
    raw = 'Вот темы:\n[{"topic": "раз"}]\nГотово.'
    assert llmjson.parse_list(raw) == [{"topic": "раз"}]


# === Обёртки, которые модель придумывает сама ===

def test_list_under_items_key():
    assert llmjson.parse_list('{"items": [{"a": 1}]}') == [{"a": 1}]


def test_list_under_any_other_key():
    """Ярлык обёртки модель выбирает каждый раз новый — он не значим."""
    assert llmjson.parse_list('{"topics": [{"a": 1}]}') == [{"a": 1}]
    assert llmjson.parse_list('{"результаты": [{"a": 1}]}') == [{"a": 1}]


def test_single_object_becomes_list_of_one():
    """Одну штуку модель отдаёт голым объектом, без массива вокруг."""
    got = llmjson.parse_list('{"topic": "одна", "why": "-"}', item_hint="topic")
    assert got == [{"topic": "одна", "why": "-"}]


def test_single_object_without_hint_is_not_guessed():
    """Без подсказки объект без списков внутри — не список из одного.

    Иначе {"error": "..."} молча превратился бы в «одну валидную запись».
    """
    with pytest.raises(llmjson.LLMJsonError):
        llmjson.parse_list('{"error": "не смог"}')


def test_empty_object_is_empty_list():
    """Пустой объект — законное «нечего предложить», не поломка."""
    assert llmjson.parse_list("{}") == []


def test_empty_list_stays_empty():
    assert llmjson.parse_list("[]") == []


# === Честные ошибки ===

def test_garbage_raises():
    with pytest.raises(llmjson.LLMJsonError):
        llmjson.parse_object("это просто текст без json")


def test_list_asked_but_object_given():
    with pytest.raises(llmjson.LLMJsonError):
        llmjson.parse_list('{"a": 1, "b": 2}')


def test_object_asked_but_list_given():
    with pytest.raises(llmjson.LLMJsonError):
        llmjson.parse_object('[1, 2, 3]')


def test_empty_input_raises():
    with pytest.raises(llmjson.LLMJsonError):
        llmjson.parse_object("")


def test_error_message_shows_what_came(monkeypatch):
    """Сообщение должно показывать начало ответа — иначе в логе видно
    только «не JSON», и непонятно, что именно прислала модель."""
    with pytest.raises(llmjson.LLMJsonError) as e:
        llmjson.parse_object("совершенно не json")
    assert "совершенно" in str(e.value)


def test_long_garbage_is_clipped():
    with pytest.raises(llmjson.LLMJsonError) as e:
        llmjson.parse_object("мусор " * 500)
    assert len(str(e.value)) < 400


# === Мягкий разбор для тех, кто не хочет падать ===

def test_object_or_default():
    assert llmjson.object_or({}, "не json") == {}
    assert llmjson.object_or({"a": 0}, '{"a": 1}') == {"a": 1}


def test_list_or_default():
    assert llmjson.list_or([], "не json") == []
    assert llmjson.list_or([], '[{"a": 1}]') == [{"a": 1}]
