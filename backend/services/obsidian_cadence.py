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
from . import graph_projector, memory_export, obsidian, obsidian_sync, vault_backup

logger = logging.getLogger(__name__)


async def tick() -> int:
    """Полный круг раз в час: память → хранилище → граф → GitHub.

    Цепочка из четырёх звеньев, и раньше автоматическим было ноль:
    память копировали руками, синхронизацию жали руками, проекции не было
    вовсе, отправку на GitHub тоже делали руками (последняя — 11.08.2026).
    Порвись любое звено — фаундер теряет работу при смене компьютера.

    Возвращает, сколько заметок втянуто в граф.
    """
    if not obsidian.is_configured():
        return 0

    # 1. Свежая память в хранилище — иначе копия там устаревает в тот же день
    try:
        copied = memory_export.export_to_vault()
        if copied:
            logger.info("Память: обновлено %d файлов в хранилище", copied)
    except Exception:
        logger.exception("Не удалось обновить память в хранилище")

    # 2. Хранилище в граф
    imported = 0
    try:
        result = obsidian_sync.sync_vault(settings.obsidian_vault_path, incremental=True)
        imported = int(result.get("imported", 0))
        if imported:
            logger.info("Obsidian: втянуто %d заметок, пропущено %d", imported, result.get("skipped", 0))
    except FileNotFoundError:
        # Папку унесли, переименовали или диск отключён — это не повод
        # ронять планировщик, в котором живут ночной прогон и напоминания.
        logger.warning("Хранилище Obsidian недоступно: %s", settings.obsidian_vault_path)
        return 0
    except Exception:
        logger.exception("Синхронизация Obsidian сорвалась")

    # 3. Остальные хранилища в граф — задачи, идеи, контент, память, подписки
    try:
        graph_projector.project_all()
    except Exception:
        logger.exception("Проекция хранилищ в граф сорвалась")

    # 4. Отправка на GitHub — единственное, что переживёт смерть диска
    try:
        vault_backup.push()
    except Exception:
        logger.exception("Резервная копия хранилища не ушла")

    return imported
