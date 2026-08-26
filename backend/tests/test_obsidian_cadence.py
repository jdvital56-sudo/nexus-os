"""Автосинхронизация хранилища Obsidian в «Второй мозг».

Связь односторонняя: заметки фаундера → граф знаний. Ручка
`/api/obsidian/sync` существовала с самого начала, но **её никто не звал
автоматически** — последняя синхронизация случилась 12.08.2026 вручную, и
две недели работы граф не видел. Обнаружено 25.08 по прямому вопросу
фаундера «почему Obsidian не наполняется».

Синхронизация ничего не стоит: чтение файлов, регулярки и локальный
теггер по частоте слов. Ни одного обращения к платной модели.
"""
import pytest

from backend.services import obsidian_cadence


@pytest.mark.asyncio
async def test_tick_syncs_when_configured(monkeypatch):
    calls = []

    def fake_sync(path, incremental=True):
        calls.append((path, incremental))
        return {"imported": 3, "skipped": 79, "graph_nodes": 3}

    monkeypatch.setattr(obsidian_cadence.obsidian, "is_configured", lambda: True)
    monkeypatch.setattr(obsidian_cadence.settings, "obsidian_vault_path", "C:/vault", raising=False)
    monkeypatch.setattr(obsidian_cadence.obsidian_sync, "sync_vault", fake_sync)

    imported = await obsidian_cadence.tick()

    assert imported == 3
    # Инкрементально: полный перебор 82 заметок каждый час — пустая работа
    assert calls == [("C:/vault", True)]


@pytest.mark.asyncio
async def test_tick_quiet_when_not_configured(monkeypatch):
    """Хранилище не настроено — молчим, а не падаем каждый час в логи."""
    monkeypatch.setattr(obsidian_cadence.obsidian, "is_configured", lambda: False)

    def boom(*a, **kw):
        raise AssertionError("не должно вызываться")

    monkeypatch.setattr(obsidian_cadence.obsidian_sync, "sync_vault", boom)

    assert await obsidian_cadence.tick() == 0


@pytest.mark.asyncio
async def test_tick_survives_missing_vault(monkeypatch):
    """Папку унесли или переименовали — джоба не должна ронять планировщик."""
    monkeypatch.setattr(obsidian_cadence.obsidian, "is_configured", lambda: True)
    monkeypatch.setattr(obsidian_cadence.settings, "obsidian_vault_path", "C:/нет", raising=False)

    def missing(path, incremental=True):
        raise FileNotFoundError("Vault not found")

    monkeypatch.setattr(obsidian_cadence.obsidian_sync, "sync_vault", missing)

    assert await obsidian_cadence.tick() == 0


@pytest.mark.asyncio
async def test_nothing_new_is_not_an_error(monkeypatch):
    monkeypatch.setattr(obsidian_cadence.obsidian, "is_configured", lambda: True)
    monkeypatch.setattr(obsidian_cadence.settings, "obsidian_vault_path", "C:/vault", raising=False)
    monkeypatch.setattr(
        obsidian_cadence.obsidian_sync, "sync_vault",
        lambda path, incremental=True: {"imported": 0, "skipped": 82},
    )

    assert await obsidian_cadence.tick() == 0
