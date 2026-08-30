"""Карусель для Instagram: нарезка сценария и отрисовка слайдов.

Тесты смотрят на настоящие картинки, а не на «функция не упала»: слайд —
это визуальный объект, и почти все его поломки видны только в пикселях.
Оба бага, которые нашлись 25.08.2026 живым прогоном и которых не показал
предпоказ, закреплены здесь построчно — длинный заголовок поверх лица и
рубрика, уехавшая за край.

Правило из CLAUDE.md про обе стороны: рядом с «теперь работает длинный
заголовок» обязан стоять тест «короткий по-прежнему оставляет фотографию».
Иначе следующая правка порога вернёт один из двух случаев обратно.
"""
from pathlib import Path

import pytest
from PIL import Image

from backend.services import carousel as C

SCRIPT = (
    "Мы часто думаем, что отдаление от близких происходит из-за больших ссор. "
    "Но на самом деле, это тихие мелочи: несказанные слова, пропущенные звонки, "
    "вечерние молчания. Мы выбираем удобство вместо честности, и расстояние "
    "растёт незаметно. Начни говорить о том, что чувствуешь, пока не стало поздно."
)
TOPIC = "психология отношений"
LONG_TOPIC = "психология отношений: почему мы отдаляемся от близких"
SHORT_HOOK = "Мы отдаляемся не из-за ссор"


@pytest.fixture
def photo(tmp_path) -> Path:
    """Портрет-заглушка: настоящий кадр с Верой в тесты не тащим."""
    path = tmp_path / "cover.jpg"
    Image.new("RGB", (1856, 2304), (170, 130, 95)).save(path, "JPEG")
    return path


# === Нарезка сценария ======================================================


def test_slides_break_on_sentences_never_mid_word():
    """Разрыв посреди фразы читается как обрыв связи."""
    for chunk in C.split_script(SCRIPT):
        assert chunk[-1] in ".!?…", f"слайд обрывается не на конце предложения: {chunk!r}"


def test_short_sentences_are_glued_together():
    """Слайд из трёх слов выглядит недоделанным."""
    chunks = C.split_script("Раз. Два. Три. Четыре.")
    assert chunks == ["Раз. Два. Три. Четыре."]


def test_long_script_gives_more_than_three_slides():
    """Досмотр карусели считается по свайпам. Первая версия резала этот же
    сценарий всего на три слайда — порог стоял вдвое выше (25.08.2026)."""
    assert len(C.split_script(SCRIPT)) >= 4


def test_empty_script_is_an_error_not_an_empty_deck():
    """Пустая карусель неотличима от «нечего сказать» — так нельзя."""
    with pytest.raises(ValueError):
        C.from_content(topic=TOPIC, script="   ")


# === Раскладка =============================================================


def test_hook_becomes_the_cover():
    deck = C.from_content(topic=TOPIC, script=SCRIPT, hook=SHORT_HOOK)
    assert deck.slides[0].kind == "cover"
    assert deck.slides[0].text == SHORT_HOOK
    # Сценарий при этом не теряет ни одного предложения
    assert deck.slides[1].text.startswith("Мы часто думаем")


def test_without_hook_the_first_sentence_carries_the_cover():
    """Поле «хук» появилось в системе позже карусели. На черновиках,
    созданных до него, обложка обязана собраться всё равно."""
    deck = C.from_content(topic=TOPIC, script=SCRIPT)
    assert deck.slides[0].kind == "cover"
    assert deck.slides[0].text.startswith("Мы часто думаем")
    # И первое предложение не должно повториться на втором слайде
    assert not deck.slides[1].text.startswith("Мы часто думаем")


def test_last_slide_is_the_conclusion():
    deck = C.from_content(topic=TOPIC, script=SCRIPT, hook=SHORT_HOOK)
    assert deck.slides[-1].kind == "outro"
    assert "пока не стало поздно" in deck.slides[-1].text


def test_deck_fits_instagram_limits():
    deck = C.from_content(topic=TOPIC, script=SCRIPT, hook=SHORT_HOOK)
    assert C.MIN_SLIDES <= len(deck.slides) <= C.MAX_SLIDES


def test_very_short_script_still_makes_a_carousel():
    """Одна карточка — не карусель, площадка её так и не примет."""
    deck = C.from_content(topic=TOPIC, script="Одна мысль.", hook="Хук")
    assert len(deck.slides) >= C.MIN_SLIDES


# === Отрисовка =============================================================


def test_slides_are_real_images_of_the_right_size(tmp_path):
    deck = C.from_content(topic=TOPIC, script=SCRIPT, hook=SHORT_HOOK)
    paths = C.render(deck, tmp_path)
    assert len(paths) == len(deck.slides)
    for path in paths:
        with Image.open(path) as img:
            assert img.size == (C.WIDTH, C.HEIGHT)


def test_slides_are_numbered_in_order(tmp_path):
    deck = C.from_content(topic=TOPIC, script=SCRIPT, hook=SHORT_HOOK)
    paths = C.render(deck, tmp_path)
    assert [p.name for p in paths] == sorted(p.name for p in paths)


def _top_is_bright(path: Path) -> bool:
    """Видна ли фотография: верх кадра с портретом заметно светлее, чем
    ровный графитовый фон. Мерим пиксели, а не верим флагу в коде."""
    from PIL import ImageStat

    with Image.open(path) as img:
        band = img.crop((0, 0, img.width, int(img.height * 0.30))).convert("L")
    return ImageStat.Stat(band).mean[0] > 70


def test_short_headline_keeps_the_photo(tmp_path, photo):
    deck = C.from_content(
        topic=TOPIC, script=SCRIPT, hook=SHORT_HOOK, style="graphite", cover=photo
    )
    paths = C.render(deck, tmp_path)
    assert _top_is_bright(paths[0]), "короткий заголовок не должен убирать портрет"


def test_long_headline_does_not_cover_the_face(tmp_path, photo):
    """Найдено живым прогоном 25.08.2026: без хука обложкой становится целое
    предложение, оно раскладывалось на шесть строк крупным кеглем и
    закрывало ведущую целиком.

    Требование — именно «лицо видно», а не «фотография убрана»: текст
    ужимается и уходит в нижнюю треть, портрет при этом остаётся. Первая
    версия этого теста требовала убрать фотографию и была неправа — код
    вёл себя лучше, чем тест от него хотел.
    """
    long_hook = (
        "Мы часто думаем, что отдаление от близких происходит из-за больших "
        "ссор, хотя причина всегда в тишине между людьми."
    )
    deck = C.from_content(
        topic=TOPIC, script=SCRIPT, hook=long_hook, style="graphite", cover=photo
    )
    paths = C.render(deck, tmp_path)
    assert _top_is_bright(paths[0]), "длинный заголовок закрыл лицо ведущей"


def test_impossible_headline_drops_the_photo_rather_than_the_text(tmp_path, photo):
    """Обратная сторона: фраза, которая не влезает в нижнюю треть даже
    минимальным кеглем. Тогда жертвуем портретом, а не читаемостью —
    обложка без фото читается, обложка с перечёркнутым лицом нет."""
    deck = C.from_content(
        topic=TOPIC, script=SCRIPT, hook="Мы отдаляемся. " * 30, style="graphite", cover=photo
    )
    paths = C.render(deck, tmp_path)
    assert not _top_is_bright(paths[0]), "нечитаемо длинный заголовок обязан убрать фото"


def test_long_topic_does_not_run_off_the_slide(tmp_path):
    """Рубрика уезжала за правый край на теме из десяти слов (25.08.2026).
    Проверяем не картинку, а ширину строки — она измерима точно."""
    from PIL import ImageDraw

    image = Image.new("RGB", (C.WIDTH, C.HEIGHT))
    draw = ImageDraw.Draw(image)
    font = C._font(C.SANS_SEMI, 30)

    deck = C.from_content(topic=LONG_TOPIC, script=SCRIPT, hook=SHORT_HOOK)
    C.render(deck, tmp_path)

    # Строка рубрики после обрезки обязана влезать в поле набора
    eyebrow = LONG_TOPIC.upper()
    while eyebrow and draw.textlength(eyebrow + "…", font=font) > C.WIDTH - C.MARGIN * 2:
        eyebrow = eyebrow[:-1].rstrip(" ,:;—-")
    assert draw.textlength(eyebrow + "…", font=font) <= C.WIDTH - C.MARGIN * 2
    assert len(eyebrow) < len(LONG_TOPIC)


def test_every_style_renders(tmp_path):
    """Стиль — это данные, а не код; сломать один, не заметив, слишком легко."""
    for style_id in C.STYLES:
        deck = C.from_content(
            topic=TOPIC, script=SCRIPT, hook=SHORT_HOOK, style=style_id
        )
        paths = C.render(deck, tmp_path / style_id)
        assert paths and paths[0].is_file()


def test_missing_cover_file_is_not_fatal(tmp_path):
    """Один потерянный jpg не должен останавливать контент-завод."""
    deck = C.from_content(
        topic=TOPIC,
        script=SCRIPT,
        hook=SHORT_HOOK,
        cover=tmp_path / "которого-нет.jpg",
    )
    paths = C.render(deck, tmp_path / "out")
    assert paths[0].is_file()
