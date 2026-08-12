"""Чистка текста: разметку не показываем и не читаем вслух.

Фаундер нажал «озвучить» и услышал «звёздочка звёздочка автохоткей
звёздочка». Модель ставит markdown по привычке, а синтезатор читает его
названиями символов.
"""
from backend.services.textclean import for_speech, strip_markdown


def test_bold_and_italic_lose_stars():
    assert strip_markdown("**AutoHotkey** и *важно*") == "AutoHotkey и важно"


def test_headings_lose_hashes():
    assert strip_markdown("## Заголовок\nтекст") == "Заголовок\nтекст"


def test_code_fences_disappear():
    assert strip_markdown("вот `код` и ```блок```") == "вот код и блок"


def test_links_keep_only_the_words():
    assert strip_markdown("смотри [мой сайт](https://example.com)") == "смотри мой сайт"


def test_bullets_become_dashes():
    assert strip_markdown("* первый\n* второй").splitlines()[0] == "- первый"


def test_speech_drops_leading_dashes():
    """Список из пяти пунктов иначе звучит как «тире, тире, тире»."""
    spoken = for_speech("- первый\n- второй\n- третий")

    assert spoken.startswith("первый")
    assert "-" not in spoken


def test_speech_drops_emoji():
    assert "📅" not in for_speech("📅 Поставил встречу")


def test_speech_drops_separators():
    assert "---" not in for_speech("текст\n---\nещё текст")


def test_speech_keeps_the_words():
    spoken = for_speech("**AutoHotkey** — это *инструмент* для Windows")

    assert "AutoHotkey" in spoken and "инструмент" in spoken
    assert "*" not in spoken


def test_empty_stays_empty():
    assert strip_markdown("") == ""
    assert for_speech(None or "") == ""
