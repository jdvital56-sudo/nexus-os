"""Очистка текста перед показом человеку и перед озвучкой.

Модель просят писать простым текстом, но привычка сильнее: она всё равно
ставит звёздочки для жирного и решётки для заголовков. В Телеграме это
видно как мусор, а голосом читается вслух — «звёздочка звёздочка
автохоткей звёздочка». Поэтому чистим в одном месте для всех каналов.

Раньше такая чистка жила только в hermes/bot.py и работала только для
Телеграма: веб-чат и озвучка её не видели.
"""
import re

# Заголовки, списки, разметка кода — всё, что модель ставит по привычке
_HEADING = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_UNDERLINE = re.compile(r"__(.+?)__", re.DOTALL)
_ITALIC = re.compile(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", re.DOTALL)
_BULLET = re.compile(r"^\s*[\*\+]\s+", re.MULTILINE)
_FENCE = re.compile(r"`{1,3}")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Значки и рамки: на экране они уместны, в речи — нет
_EMOJI = re.compile(
    "[" "\U0001f300-\U0001faff" "\U00002600-\U000027bf" "\U0001f1e6-\U0001f1ff" "←-⇿"
    "⬀-⯿" "️" "]+",
    flags=re.UNICODE,
)


def strip_markdown(text: str) -> str:
    """Убирает разметку, оставляя сам текст. Ссылки превращает в подпись."""
    if not text:
        return ""
    text = _HEADING.sub("", text)
    text = _BOLD.sub(r"\1", text)
    text = _UNDERLINE.sub(r"\1", text)
    text = _ITALIC.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _BULLET.sub("- ", text)
    text = _FENCE.sub("", text)
    return text.strip()


def for_speech(text: str) -> str:
    """Готовит текст к озвучке.

    Кроме разметки убираем значки и всё, что синтезатор прочитает вслух как
    название символа. Тире в начале строки — тоже: список из пяти пунктов
    иначе звучит как «тире, тире, тире».
    """
    text = strip_markdown(text)
    text = _EMOJI.sub(" ", text)
    text = re.sub(r"^[\s\-—•]+", "", text, flags=re.MULTILINE)
    # Разделители из дефисов и подчёркиваний читаются как длинное мычание
    text = re.sub(r"[-_=]{3,}", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
