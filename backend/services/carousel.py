# -*- coding: utf-8 -*-
"""Карусель для Instagram: сценарий превращается в стопку слайдов-картинок.

25.08.2026, по прямой просьбе фаундера. Контент-завод до этого умел ровно
одну картинку на пост (`ContentItem.image_file`), а карусель — это 2–10
слайдов, связанных одним стилем и читаемых подряд.

**Почему рисуем локально, а не генерируем через модель.** Слайд карусели —
это текст на фоне, а не картина. Диффузионные модели рисуют текст плохо и
непредсказуемо (кириллицу — особенно), стоят денег за каждый кадр и не
дают повторяемости: два соседних слайда выйдут разного оттенка. Pillow
рисует ровно то, что попросили, бесплатно, за миллисекунды и одинаково
каждый раз. Модель нужна для фона, если фон нужен — но не для букв.

**Размер 1080×1350.** Instagram допускает в ленте до 4:5, и это самый
высокий разрешённый кадр — значит самая большая доля экрана телефона.
Квадрат 1080×1080 отдаёт четверть высоты просто так.

Шрифты берём системные (Georgia + Open Sans): оба с кириллицей, оба уже
стоят на машине. Скачивать Montserrat ради красоты — лишняя зависимость в
проекте, который должен работать без интернета.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 1080, 1350

# Instagram принимает от 2 до 10 карточек в карусели. Меньше двух — это не
# карусель, больше десяти площадка просто не примет.
MIN_SLIDES, MAX_SLIDES = 2, 10

FONTS_DIR = Path("C:/Windows/Fonts")

# Georgia — засечный, спокойный, «человеческий»: под психологический канал
# он читается как разговор, а не как реклама. Open Sans — для мелкого
# текста, где засечки только мешают.
SERIF_BOLD = FONTS_DIR / "georgiab.ttf"
SERIF = FONTS_DIR / "georgia.ttf"
SANS = FONTS_DIR / "OpenSans-Regular.ttf"
SANS_SEMI = FONTS_DIR / "OpenSans-SemiBold.ttf"


@dataclass
class Style:
    """Один визуальный стиль карусели."""

    id: str
    label: str
    bg: tuple[int, int, int]
    ink: tuple[int, int, int]
    accent: tuple[int, int, int]
    # Приглушённый цвет для номера слайда и хэндла — он не должен спорить
    # с основным текстом за внимание
    faint: tuple[int, int, int]


# Палитра взята не с потолка: это цвета кадра с Верой — тёплый бежевый фон
# и графитовая водолазка (см. content-factory/vera-character/vera-ref-v1.jpg).
# Карусель и ролики одного канала должны выглядеть одним каналом.
STYLES: dict[str, Style] = {
    "beige": Style(
        id="beige",
        label="Тёплый беж",
        bg=(214, 180, 143),
        ink=(38, 42, 43),
        accent=(38, 42, 43),
        faint=(120, 100, 80),
    ),
    "graphite": Style(
        id="graphite",
        label="Графит",
        bg=(35, 40, 42),
        ink=(232, 220, 203),
        accent=(214, 180, 143),
        faint=(130, 130, 122),
    ),
    "paper": Style(
        id="paper",
        label="Бумага",
        bg=(243, 238, 230),
        ink=(35, 40, 42),
        accent=(158, 112, 64),
        faint=(150, 143, 132),
    ),
}

DEFAULT_STYLE = "beige"

MARGIN = 96

# Порог длины слайда — не эстетика, а механика площадки. Досмотр карусели
# считается по свайпам: три плотных слайда собирают меньше, чем шесть
# коротких, потому что каждый свайп — сигнал вовлечённости. Плюс абзац на
# полэкрана в телефоне просто пролистывают. 130 символов — примерно одна
# мысль вслух; первая версия стояла на 220 и резала сценарий всего на три
# слайда, что и видно было на предпоказе.
MAX_CHARS_PER_SLIDE = 110


@dataclass
class Slide:
    """Один слайд. `kind` меняет вёрстку, не только текст."""

    text: str
    kind: str = "body"  # cover | body | outro
    eyebrow: str = ""  # мелкая строка над заголовком (тема, рубрика)
    background: Path | None = None  # картинка под текст, если есть
    _index: int = 0
    _total: int = 0


@dataclass
class Carousel:
    slides: list[Slide] = field(default_factory=list)
    style: str = DEFAULT_STYLE
    handle: str = ""


def cover_photo() -> Path | None:
    """Портрет ведущей для обложки. None — обложка будет типографской.

    Порядок поиска тот же, что у голосов Piper, и по той же причине: это
    машинные данные канала, а не код, и рабочих деревьев бывает несколько.
    Отсутствие файла — не ошибка: карусель обязана собираться и без
    портрета, иначе один потерянный jpg останавливает весь контент-завод.
    """
    import os

    override = os.getenv("NEXUS_CAROUSEL_COVER", "")
    if override:
        path = Path(override)
        return path if path.is_file() else None

    shared = Path.home() / ".nexsys" / "carousel_cover.jpg"
    if shared.is_file():
        return shared

    # Место, где портрет Веры завела соседняя сессия 25.08.2026
    project = Path(__file__).resolve().parents[2] / "content-factory" / "vera-character"
    for candidate in sorted(project.glob("*.jpg")):
        return candidate
    return None


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Переносит текст по словам под заданную ширину.

    Своя реализация, а не `textwrap`: тот считает символы, а нам нужны
    пиксели — в «Ш» и «i» ширина отличается втрое, и по символам строка то
    вылезает за поле, то не добирает до него.
    """
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: Path,
    max_width: int,
    max_height: int,
    sizes: range,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Подбирает самый крупный кегль, при котором текст ещё помещается.

    Перебор от большего к меньшему, а не расчёт по формуле: перенос по
    словам меняет число строк скачками, и аналитической зависимости между
    кеглем и высотой блока просто нет.
    """
    for size in sorted(sizes, reverse=True):
        font = _font(font_path, size)
        lines = _wrap(draw, text, font, max_width)
        leading = int(size * 1.28)
        if leading * len(lines) <= max_height:
            return font, lines, leading
    # Не влезло даже минимальным — отдаём минимальный: пусть лучше слайд
    # будет плотным, чем пустым.
    size = min(sizes)
    font = _font(font_path, size)
    return font, _wrap(draw, text, font, max_width), int(size * 1.28)


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font,
    leading: int,
    x: int,
    y: int,
    fill,
) -> int:
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += leading
    return y


def render_slide(slide: Slide, style: Style, handle: str = "") -> Image.Image:
    """Рисует один слайд и возвращает картинку."""
    image = Image.new("RGB", (WIDTH, HEIGHT), style.bg)

    if slide.background is not None and slide.background.is_file():
        image = _with_background(image, slide.background, style)

    draw = ImageDraw.Draw(image)
    inner = WIDTH - MARGIN * 2

    # Обложка кричит, остальные слайды разговаривают: разный кегль — это не
    # украшение, а то, ради чего человек вообще останавливает пролистывание.
    if slide.kind == "cover":
        sizes = range(56, 108, 4)
        font_path = SERIF_BOLD
    elif slide.kind == "outro":
        sizes = range(44, 76, 4)
        font_path = SERIF_BOLD
    else:
        sizes = range(40, 72, 4)
        font_path = SERIF

    top = MARGIN + (150 if slide.eyebrow else 0)
    available = HEIGHT - top - MARGIN - 120  # 120 — подвал с номером и хэндлом

    has_photo = slide.background is not None and slide.background.is_file()
    if has_photo:
        # Поверх фотографии текст живёт только в нижней трети: выше — лицо,
        # ради которого фотографию и поставили. Живой прогон 25.08.2026:
        # длинный заголовок разложился на шесть строк и закрыл Веру
        # целиком — на предпоказе с коротким хуком этого видно не было.
        available = int(HEIGHT * 0.34)

    font, lines, leading = _fit(draw, slide.text, font_path, inner, available, sizes)

    block_height = leading * len(lines)
    if has_photo and block_height > available:
        # Не влез даже минимальным кеглем — значит эта фраза несовместима с
        # фотографией. Портретом жертвуем, текстом нет: обложка без фото
        # читается, обложка с перечёркнутым лицом — нет.
        image = Image.new("RGB", (WIDTH, HEIGHT), style.bg)
        draw = ImageDraw.Draw(image)
        has_photo = False
        available = HEIGHT - top - MARGIN - 120
        font, lines, leading = _fit(draw, slide.text, font_path, inner, available, sizes)
        block_height = leading * len(lines)

    if has_photo:
        # Поверх фотографии текст уходит вниз, а не в середину: в середине
        # кадра лицо, и заголовок ложится ровно на него. Проверено глазами
        # на предпоказе 25.08.2026 — первый вариант перечёркивал Веру.
        y = HEIGHT - MARGIN - 150 - block_height
    else:
        # Взгляд на телефоне попадает в середину экрана, и «висящая» вверху
        # строка теряется.
        y = top + max(0, (available - block_height) // 2)

    if slide.eyebrow:
        # Поверх фотографии приглушённый цвет рубрики пропадает: вверху
        # кадра светло, а `faint` рассчитан на ровный фон. Найдено глазами
        # на предпоказе — надпись «ПСИХОЛОГИЯ ОТНОШЕНИЙ» просто исчезла.
        eyebrow_ink = style.ink if has_photo else style.faint
        eyebrow_font = _font(SANS_SEMI, 30)
        # Рубрика — одна строка и только одна: тема черновика бывает
        # длинной («психология отношений: почему мы отдаляемся от близких»),
        # и на живом прогоне она уехала за правый край слайда. Переносить
        # её на вторую строку нельзя — она подпирает заголовок.
        eyebrow = slide.eyebrow.upper()
        while eyebrow and draw.textlength(eyebrow + "…", font=eyebrow_font) > inner:
            eyebrow = eyebrow[:-1].rstrip(" ,:;—-")
        if eyebrow != slide.eyebrow.upper():
            eyebrow += "…"
        draw.text((MARGIN, MARGIN + 10), eyebrow, font=eyebrow_font, fill=eyebrow_ink)
        draw.line(
            [(MARGIN, MARGIN + 66), (MARGIN + 90, MARGIN + 66)],
            fill=style.accent,
            width=4,
        )

    _draw_lines(draw, lines, font, leading, MARGIN, y, style.ink)

    # Обложке — короткая черта под текстом: она говорит «дальше есть ещё»
    if slide.kind == "cover":
        draw.line(
            [(MARGIN, y + block_height + 48), (MARGIN + 160, y + block_height + 48)],
            fill=style.accent,
            width=6,
        )

    _draw_footer(draw, slide, style, handle)
    return image


def _with_background(base: Image.Image, path: Path, style: Style) -> Image.Image:
    """Кладёт фотографию под текст и гасит её, чтобы буквы читались.

    Без затемнения текст на фото нечитаем ровно там, где фото интереснее
    всего — на лице и светлых пятнах. Градиент, а не равномерная заливка:
    низ слайда, где стоит подвал, должен быть темнее верха.
    """
    photo = Image.open(path).convert("RGB")
    # Заполняем кадр целиком, лишнее обрезаем по центру
    scale = max(base.width / photo.width, base.height / photo.height)
    photo = photo.resize((round(photo.width * scale), round(photo.height * scale)), Image.LANCZOS)
    left = (photo.width - base.width) // 2
    top = (photo.height - base.height) // 2
    photo = photo.crop((left, top, left + base.width, top + base.height))

    # Градиент, а не равномерная заливка: текст стоит внизу, значит гасить
    # надо низ. Верх остаётся почти чистым — иначе ведущая, ради которой
    # фото и ставили, превращается в тёмное пятно (видно на первом
    # предпоказе 25.08.2026: было 40% уже сверху).
    veil = Image.new("L", (1, base.height))
    for y in range(base.height):
        share = y / base.height
        # 12% сверху → 92% внизу, с ускорением к низу
        veil.putpixel((0, y), int(255 * min(0.92, 0.12 + 0.80 * share**1.7)))
    veil = veil.resize((base.width, base.height))

    shade = Image.new("RGB", base.size, style.bg if sum(style.bg) < 300 else (24, 26, 27))
    return Image.composite(shade, photo, veil)


def _draw_footer(draw: ImageDraw.ImageDraw, slide: Slide, style: Style, handle: str) -> None:
    font = _font(SANS, 28)
    y = HEIGHT - MARGIN - 30
    if handle:
        draw.text((MARGIN, y), handle, font=font, fill=style.faint)
    if slide._total > 1:
        counter = f"{slide._index}/{slide._total}"
        width = draw.textlength(counter, font=font)
        draw.text((WIDTH - MARGIN - width, y), counter, font=font, fill=style.faint)


def render(carousel: Carousel, out_dir: Path, prefix: str = "slide") -> list[Path]:
    """Рисует всю карусель. Возвращает пути к слайдам по порядку."""
    if not carousel.slides:
        raise ValueError("В карусели нет ни одного слайда")

    style = STYLES.get(carousel.style) or STYLES[DEFAULT_STYLE]
    out_dir.mkdir(parents=True, exist_ok=True)

    total = len(carousel.slides)
    paths: list[Path] = []
    for number, slide in enumerate(carousel.slides, start=1):
        slide._index, slide._total = number, total
        path = out_dir / f"{prefix}-{number:02d}.jpg"
        # JPEG, не PNG: Instagram всё равно пережмёт, а PNG со слайдом на
        # 1080×1350 весит в разы больше без единого видимого отличия.
        render_slide(slide, style, carousel.handle).save(path, "JPEG", quality=92)
        paths.append(path)

    logger.info("Карусель: %d слайдов в %s", total, out_dir)
    return paths


def split_script(script: str, hook: str = "", limit: int = MAX_CHARS_PER_SLIDE) -> list[str]:
    """Режет сценарий на реплики по слайдам — по предложениям, не по буквам.

    Разрыв посреди фразы читается как обрыв связи, поэтому границей слайда
    может быть только конец предложения. Короткие предложения склеиваются,
    пока помещаются: слайд из трёх слов выглядит недоделанным.
    """
    import re

    text = (script or "").strip()
    if not text:
        return [hook] if hook else []

    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text) if s.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= limit or not current:
            current = candidate
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def from_content(
    topic: str,
    script: str,
    hook: str = "",
    style: str = DEFAULT_STYLE,
    handle: str = "",
    cover: Path | None = None,
) -> Carousel:
    """Собирает карусель из полей черновика контент-завода.

    Раскладка выбрана по тому, как карусель читают: обложка ловит взгляд,
    середина разворачивает мысль по одной за слайд, последний слайд —
    вывод, на котором человек либо сохраняет пост, либо нет.

    Хук берётся из черновика, если он там есть. Если поля «хук» ещё нет
    (оно появилось в соседней ветке 25.08.2026 и в main приходит позже) —
    обложкой становится первое предложение сценария. Пустая обложка была
    бы хуже любого запасного варианта.
    """
    chunks = split_script(script)
    if not chunks:
        raise ValueError("Нечего показывать: у черновика пустой сценарий")

    headline = (hook or "").strip() or chunks[0]
    body = chunks if hook.strip() else chunks[1:]

    slides = [Slide(text=headline, kind="cover", eyebrow=topic, background=cover)]
    slides += [Slide(text=chunk, kind="body") for chunk in body[:-1]]
    if body:
        slides.append(Slide(text=body[-1], kind="outro"))

    # Одна карточка — это не карусель, площадка её не примет как карусель.
    # Такое бывает на очень коротком сценарии: тогда честнее отдать пост
    # из двух карточек, чем притворяться, что карусель собралась.
    if len(slides) < MIN_SLIDES:
        slides.append(Slide(text=chunks[-1], kind="outro"))

    return Carousel(slides=slides[:MAX_SLIDES], style=style, handle=handle)
