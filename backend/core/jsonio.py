"""Чтение и запись JSON-хранилищ в UTF-8 (инвариант I-8).

Без явной кодировки Python на Windows пишет файлы в системной локали
(cp1251), и данные с кириллицей становятся нечитаемы в Docker и на любой
UTF-8 машине. Здесь запись всегда UTF-8, а чтение умеет подобрать
старые файлы и переписать их — миграция происходит сама, без скриптов.

23.08.2026, по итогам внешнего аудита (проверено самостоятельно, не на
слово): запись была `Path.write_text()` напрямую — крэш/отключение
питания посреди записи оставлял битый файл, а read_json на битом JSON
молча отдавал default, после чего первый же _save() перезаписывал файл
пустым списком. Повреждение → тихое уничтожение всей памяти/задач/графа.
Плюс ни один вызывающий код нигде не был защищён от гонки: два канала
(веб-чат и Telegram — РАЗНЫЕ процессы) читают-меняют-пишут один файл без
лока, второй писатель тихо теряет правку первого. write_json теперь
атомарна (tmp + os.replace — устоявшийся паттерн для файлов, которые
нельзя терять). Настоящую защиту от гонки чтения-изменения-записи даёт
locked_update() ниже — im.py-сервисы переезжают на неё по одному,
начиная с самого важного (services/memory.py), не все сразу.
"""
import json
import logging
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from filelock import FileLock

logger = logging.getLogger(__name__)

# Кодировка, в которой Windows писал файлы до этого исправления
_LEGACY_ENCODING = "cp1251"

# Сколько ждём чужой лок, прежде чем сдаться — лучше явная ошибка, чем
# зависший навсегда запрос, если держатель лока упал и не снял его.
_LOCK_TIMEOUT_SECONDS = 10


def read_json(path: Path, default: Any = None) -> Any:
    """Читает JSON. Файл в старой кодировке молча переписывается в UTF-8.

    Битый JSON НЕ отдаётся молча как default и забывается: файл
    переименовывается в *.corrupt-<время>, чтобы было что расследовать и
    откуда восстанавливать — раньше следующая же запись стирала повреждение
    вместе со всем, что было в файле до него.
    """
    path = Path(path)
    if not path.exists():
        return default

    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode(_LEGACY_ENCODING)
        logger.info("Файл %s был в %s — переписываю в UTF-8", path, _LEGACY_ENCODING)
        path.write_text(text, encoding="utf-8")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        corrupt_path = path.with_name(f"{path.name}.corrupt-{stamp}")
        try:
            path.rename(corrupt_path)
            logger.error(
                "Файл %s повреждён — сохранён как %s для расследования, "
                "беру значение по умолчанию",
                path, corrupt_path,
            )
        except OSError:
            logger.error("Файл %s повреждён и не удалось сохранить копию", path)
        return default


def write_json(path: Path, data: Any) -> None:
    """Пишет JSON в UTF-8, не экранируя кириллицу — атомарно.

    Пишем во временный файл в той же папке (та же файловая система —
    иначе os.replace не атомарна) и переименовываем поверх настоящего.
    os.replace — атомарная операция и на Windows, и на POSIX: читатель
    в любой момент видит либо целиком старый файл, либо целиком новый,
    никогда середину записи.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _lock_path(path: Path) -> Path:
    return Path(path).with_name(f"{Path(path).name}.lock")


@contextmanager
def lock(path: Path):
    """Межпроцессный лок на один JSON-файл — веб-чат и Telegram-бот это
    разные процессы, threading.Lock между ними не помог бы вообще."""
    with FileLock(str(_lock_path(path)), timeout=_LOCK_TIMEOUT_SECONDS):
        yield


def locked_update(path: Path, mutate: Callable[[Any], Any], default: Any = None) -> Any:
    """Атомарное чтение-изменение-запись под межпроцессным локом.

    `mutate(data) -> data` получает то, что вернул read_json (или default,
    если файла нет/он битый), и возвращает то, что нужно сохранить.
    Исключение внутри mutate — запись не происходит, лок всё равно снят.
    """
    with lock(path):
        data = read_json(path, default)
        result = mutate(data)
        write_json(path, result)
        return result
