"""Чтение и запись JSON-хранилищ в UTF-8 (инвариант I-8).

Без явной кодировки Python на Windows пишет файлы в системной локали
(cp1251), и данные с кириллицей становятся нечитаемы в Docker и на любой
UTF-8 машине. Здесь запись всегда UTF-8, а чтение умеет подобрать
старые файлы и переписать их — миграция происходит сама, без скриптов.
"""
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Кодировка, в которой Windows писал файлы до этого исправления
_LEGACY_ENCODING = "cp1251"


def read_json(path: Path, default: Any = None) -> Any:
    """Читает JSON. Файл в старой кодировке молча переписывается в UTF-8."""
    if not Path(path).exists():
        return default

    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode(_LEGACY_ENCODING)
        logger.info("Файл %s был в %s — переписываю в UTF-8", path, _LEGACY_ENCODING)
        Path(path).write_text(text, encoding="utf-8")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Файл %s повреждён, беру значение по умолчанию", path)
        return default


def write_json(path: Path, data: Any) -> None:
    """Пишет JSON в UTF-8, не экранируя кириллицу."""
    Path(path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
