"""Автосинхронизация хранилища Obsidian во «Второй мозг».

Связь односторонняя и намеренно: заметки фаундера → граф знаний. Обратно
система в хранилище не пишет (кроме явной команды «/note» в разговоре).

Ручка `/api/obsidian/sync` была с самого начала, но **её никто не звал
автоматически**. Последняя синхронизация — 12.08.2026 вручную; к 25.08
граф отставал на две недели, и фаундер справедливо спросил, почему
«Второй мозг» не наполняется. Джоба закрывает ровно этот разрыв.

Денег не стоит: чтение файлов, регулярки по тегам и `[[ссылкам]]`,
теггер по частоте слов — всё локально, ни одного обращения к модели.
"""
import logging

from ..core.config import settings
from . import obsidian, obsidian_sync

logger = logging.getLogger(__name__)


async def tick() -> int:
    """Догоняет хранилище. Возвращает, сколько заметок втянуто.

    Инкрементально: неизменившиеся файлы пропускаются по времени правки,
    поэтому обычный тик стоит один обход каталога и ничего больше.
    """
    if not obsidian.is_configured():
        return 0

    try:
        result = obsidian_sync.sync_vault(settings.obsidian_vault_path, incremental=True)
    except FileNotFoundError:
        # Папку унесли, переименовали или диск отключён — это не повод
        # ронять планировщик, в котором живут ночной прогон и напоминания.
        logger.warning("Хранилище Obsidian недоступно: %s", settings.obsidian_vault_path)
        return 0
    except Exception:
        logger.exception("Синхронизация Obsidian сорвалась")
        return 0

    imported = int(result.get("imported", 0))
    if imported:
        logger.info(
            "Obsidian: втянуто %d заметок, пропущено %d",
            imported,
            result.get("skipped", 0),
        )
    return imported
