"""Копирование памяти агента в хранилище Obsidian.

Память живёт в рабочем каталоге Claude Code, а хранилище — единственное
место, откуда она попадает и во «Второй мозг», и на GitHub. Пока копирование
делалось руками, копия устаревала в тот же день, а 25.08.2026 выяснилось,
что она вообще одиннадцать дней не обновлялась: локальная копия хранилища
сидела на другой ветке git.

Копируем только изменившееся — сравниваем содержимое, а не время правки:
время меняется от простого пересохранения, и хранилище копило бы пустые
коммиты каждый час.
"""
import logging
import os
from pathlib import Path

from ..core.config import settings

logger = logging.getLogger(__name__)

# Где Claude Code держит память этой машины. Путь задаётся переменной —
# у каждой машины он свой, и зашивать его в код нельзя.
MEMORY_DIR_ENV = "NEXUS_AGENT_MEMORY_DIR"

VAULT_SUBFOLDER = "agent-memory"


def memory_dir() -> Path | None:
    raw = os.getenv(MEMORY_DIR_ENV, "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def export_to_vault() -> int:
    """Кладёт свежие файлы памяти в хранилище. Возвращает число обновлённых.

    Ничего не удаляет: файл, убранный из памяти, остаётся в хранилище и в
    истории git. Стирать чужую копию по своей инициативе — не наше дело,
    а история решений тем и ценна, что не переписывается задним числом.
    """
    src = memory_dir()
    if src is None:
        return 0

    vault = (settings.obsidian_vault_path or "").strip()
    if not vault:
        return 0

    dst = Path(vault) / VAULT_SUBFOLDER
    try:
        dst.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("Не могу создать %s", dst)
        return 0

    copied = 0
    for f in sorted(src.glob("*.md")):
        target = dst / f.name
        try:
            new = f.read_bytes()
            if target.exists() and target.read_bytes() == new:
                continue  # не трогаем — иначе пустой коммит каждый час
            target.write_bytes(new)
            copied += 1
        except OSError:
            logger.warning("Файл памяти %s не скопирован", f.name, exc_info=True)

    return copied
