"""Открытие программ и сайтов голосом.

24.08.2026: фаундер сказал «Джарвис должен исполнять все мои команды —
открыть браузер и дальше тоже». До этого список был из четырёх программ
(калькулятор, блокнот, проводник, паинт), всё остальное отвечало «не могу».
Теперь ищем ярлык в меню «Пуск» — то же, что видит человек, нажав «Пуск».

Меню «Пуск» тут настоящее, машинное: тесты не должны падать на чужой
машине, поэтому проверяем логику поиска на подставном списке, а не на
том, что реально установлено.
"""
from pathlib import Path

import pytest

from backend.services import system_open


@pytest.fixture
def fake_start_menu(monkeypatch):
    """Подставной список установленного — как если бы это был «Пуск»."""
    apps = {
        "obs studio": Path("C:/Menu/OBS Studio.lnk"),
        "obsidian": Path("C:/Menu/Obsidian.lnk"),
        "google chrome": Path("C:/Menu/Google Chrome.lnk"),
        "telegram": Path("C:/Menu/Telegram.lnk"),
        "деинсталлировать telegram": Path("C:/Menu/Uninstall Telegram.lnk"),
        "steam": Path("C:/Menu/Steam.lnk"),
        "uninstall zoom workplace": Path("C:/Menu/Uninstall Zoom.lnk"),
        "zoom workplace": Path("C:/Menu/Zoom Workplace.lnk"),
    }
    monkeypatch.setattr(system_open, "_installed_apps", lambda: apps)
    return apps


def test_finds_app_by_english_name(fake_start_menu):
    kind, target = system_open.resolve("steam")
    assert kind == "shortcut"
    assert target.endswith("Steam.lnk")


def test_finds_app_by_russian_spoken_name(fake_start_menu):
    """Фаундер говорит по-русски, ярлыки почти все латиницей."""
    kind, target = system_open.resolve("хром")
    assert kind == "shortcut"
    assert target.endswith("Google Chrome.lnk")


def test_short_name_matches_whole_word_not_substring(fake_start_menu):
    """«обс» — это OBS Studio, а не Obsidian.

    Первая версия сортировала совпадения по длине имени, и «obsidian»
    (8 букв) выигрывал у «obs studio» (10) — Джарвис открывал не ту
    программу. Найдено живым прогоном 24.08.2026.
    """
    kind, target = system_open.resolve("обс")
    assert kind == "shortcut"
    assert target.endswith("OBS Studio.lnk")


def test_full_name_still_finds_the_other_app(fake_start_menu):
    kind, target = system_open.resolve("обсидиан")
    assert target.endswith("Obsidian.lnk")


def test_uninstaller_is_never_launched(fake_start_menu):
    """Деинсталлятор лежит в том же меню и часто короче по имени."""
    kind, target = system_open.resolve("telegram")
    assert "Uninstall" not in target
    assert target.endswith("Telegram.lnk")


def test_installed_app_wins_over_website(fake_start_menu):
    """«телеграм» -> настольное приложение, раз оно стоит; веб-версия
    остаётся запасным вариантом, если программы нет."""
    kind, target = system_open.resolve("телеграм")
    assert kind == "shortcut"
    assert target.endswith("Telegram.lnk")


def test_website_used_when_app_is_not_installed(monkeypatch):
    monkeypatch.setattr(system_open, "_installed_apps", lambda: {})
    kind, target = system_open.resolve("телеграм")
    assert kind == "site"
    assert "telegram" in target


def test_filler_words_are_ignored(fake_start_menu):
    """«открой МНЕ хром ПОЖАЛУЙСТА» — вокруг названия бывает шум."""
    kind, target = system_open.resolve("мне хром пожалуйста")
    assert target.endswith("Google Chrome.lnk")


def test_music_opens_youtube_music(fake_start_menu):
    """Фаундер выбрал YouTube Music как единственный плеер (24.08.2026)."""
    kind, target = system_open.resolve("музыку")
    assert kind == "site"
    assert target == system_open.MUSIC_DEFAULT


def test_url_still_works(fake_start_menu):
    kind, target = system_open.resolve("github.com")
    assert kind == "site"
    assert target == "https://github.com"


def test_unknown_returns_none(fake_start_menu):
    assert system_open.resolve("совершенно неизвестная штука") is None


def test_unknown_answer_does_not_promise_a_short_list(fake_start_menu):
    """Старый ответ перечислял четыре программы как всё, что доступно —
    теперь это неправда."""
    answer = system_open.open_target("совершенно неизвестная штука")
    assert "калькулятор" not in answer
    assert "Пуск" in answer
