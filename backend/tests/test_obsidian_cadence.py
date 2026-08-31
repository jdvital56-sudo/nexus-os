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


# === Заслон от утечки секретов при автоотправке ===

def test_secret_scan_catches_real_keys():
    from backend.services import vault_backup as vb

    assert vb.find_secrets("ключ sk-abcdefghij0123456789xyz тут")
    assert vb.find_secrets("AIzaSyA1234567890abcdefghijklmnopqrstu")
    assert vb.find_secrets("token 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw")


def test_secret_scan_ignores_variable_names():
    """Имена переменных в памяти встречаются постоянно — это не секреты."""
    from backend.services import vault_backup as vb

    text = "Ключ лежит в .env под FAL_KEY, бот в TELEGRAM_BOT_TOKEN, DEEPSEEK_API_KEY"
    assert vb.find_secrets(text) == []


def test_secret_scan_does_not_echo_the_secret():
    """Напечатать секрет в отчёте об утечке — это ещё одна утечка."""
    from backend.services import vault_backup as vb

    found = vb.find_secrets("sk-abcdefghij0123456789xyz")
    assert found
    assert "abcdefghij0123456789xyz" not in " ".join(found)


def test_push_refuses_when_secret_found(monkeypatch):
    from backend.services import vault_backup as vb

    calls = []

    def fake_git(*args):
        calls.append(args)
        import subprocess
        out = ""
        if args[0] == "status":
            out = " M note.md"
        elif args[0] == "diff":
            out = "+ ключ sk-abcdefghij0123456789xyz"
        return subprocess.CompletedProcess(args, 0, out, "")

    monkeypatch.setattr(vb, "_git", fake_git)
    monkeypatch.setattr(vb.settings, "obsidian_vault_path", "C:/vault", raising=False)

    assert vb.push() is False
    assert ("reset",) in calls          # снял со сцены
    assert not any(a[0] == "push" for a in calls)   # и НЕ отправил
