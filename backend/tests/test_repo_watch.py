"""Сторож репозиториев: напоминание про работу, не уехавшую в git.

Тесты работают с НАСТОЯЩИМИ временными репозиториями, а не с подменённым
`git`. Смысл сторожа целиком в том, как он разбирает вывод git, — подменив
git, мы проверяли бы собственную выдумку о его выводе.

Правило CLAUDE.md про обе стороны здесь особенно важно: у сторожа есть
порог, а порог всегда ломается парой. Рядом с «старое сообщает» обязано
стоять «свежее молчит», иначе следующая правка порога превратит его либо в
спам на каждую правку, либо в молчание навсегда — и оба раза это заметит
только фаундер.
"""
import subprocess
import time
from pathlib import Path

import pytest

from backend.services import repo_watch


def _run(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


@pytest.fixture
def repo(tmp_path) -> Path:
    """Настоящий git-репозиторий с одним коммитом."""
    path = tmp_path / "проект"  # кириллица намеренно: у фаундера так везде
    path.mkdir()
    _run(path, "init", "-b", "main")
    _run(path, "config", "user.email", "test@test")
    _run(path, "config", "user.name", "Тест")
    (path / "README.md").write_text("начало", encoding="utf-8")
    _run(path, "add", "README.md")
    _run(path, "commit", "-m", "первый")
    return path


def _age(path: Path, hours: float) -> None:
    """Состарить файл: сторож смотрит время изменения, а не время коммита."""
    old = time.time() - hours * 3600
    import os

    os.utime(path, (old, old))


# === Порог: обе стороны ====================================================


def test_fresh_work_stays_quiet(repo, monkeypatch):
    """Правка, сделанная только что, — это человек за работой, а не потеря.
    Напоминать про неё значит приучить не читать сообщения."""
    monkeypatch.setattr(repo_watch, "watched_repos", lambda: [repo])
    (repo / "новый.py").write_text("код", encoding="utf-8")
    assert repo_watch.digest_text() == ""


def test_stale_work_is_reported(repo, monkeypatch):
    """Ради этого сторож и написан: 11 дней работы лежали незамеченными."""
    monkeypatch.setattr(repo_watch, "watched_repos", lambda: [repo])
    stale = repo / "забытый.py"
    stale.write_text("код", encoding="utf-8")
    _age(stale, repo_watch.STALE_HOURS + 1)

    text = repo_watch.digest_text()
    assert "проект" in text
    assert "забытый.py" in text, "имя файла с кириллицей должно читаться, а не быть в escape"


def test_threshold_edge_is_inclusive(repo, monkeypatch):
    """Ровно на пороге — уже сообщаем. Иначе работа возрастом в сутки
    зависает в щели между «свежая» и «старая»."""
    monkeypatch.setattr(repo_watch, "watched_repos", lambda: [repo])
    edge = repo / "ровно.py"
    edge.write_text("код", encoding="utf-8")
    _age(edge, repo_watch.STALE_HOURS)
    assert repo_watch.digest_text() != ""


# === Неотправленные коммиты ================================================


def test_unpushed_commits_are_reported_even_when_fresh(repo, tmp_path, monkeypatch):
    """Законченная работа на одной машине — уже риск, сколько бы ей ни было
    минут. Здесь порог возраста не применяется намеренно."""
    bare = tmp_path / "origin.git"
    _run(repo, "init", "--bare", str(bare))
    _run(repo, "remote", "add", "origin", str(bare))
    _run(repo, "push", "-u", "origin", "main")

    (repo / "готово.py").write_text("код", encoding="utf-8")
    _run(repo, "add", "готово.py")
    _run(repo, "commit", "-m", "закончено, но не отправлено")

    monkeypatch.setattr(repo_watch, "watched_repos", lambda: [repo])
    text = repo_watch.digest_text()
    assert "не отправлено коммитов: 1" in text


def test_everything_pushed_means_silence(repo, tmp_path, monkeypatch):
    bare = tmp_path / "origin.git"
    _run(repo, "init", "--bare", str(bare))
    _run(repo, "remote", "add", "origin", str(bare))
    _run(repo, "push", "-u", "origin", "main")

    monkeypatch.setattr(repo_watch, "watched_repos", lambda: [repo])
    assert repo_watch.digest_text() == ""


# === Устойчивость ==========================================================


def test_clean_repo_says_nothing(repo, monkeypatch):
    monkeypatch.setattr(repo_watch, "watched_repos", lambda: [repo])
    assert repo_watch.digest_text() == ""


def test_not_a_repo_is_skipped(tmp_path, monkeypatch):
    """Путь без .git не должен ронять обход остальных."""
    monkeypatch.setenv("NEXUS_WATCHED_REPOS", str(tmp_path / "которого-нет"))
    assert repo_watch.watched_repos() == []


def test_broken_git_does_not_crash(repo, monkeypatch):
    """Залипший индекс или отсутствующий git — сторож обязан промолчать,
    а не уронить весь планировщик вместе с остальными заданиями."""

    def boom(*args, **kwargs):
        raise OSError("git не найден")

    monkeypatch.setattr(repo_watch.subprocess, "run", boom)
    monkeypatch.setattr(repo_watch, "watched_repos", lambda: [repo])
    assert repo_watch.digest_text() == ""


def test_deleted_file_does_not_break_age_check(repo, monkeypatch):
    """`git status` показывает удалённый файл, а `stat` по нему падает."""
    monkeypatch.setattr(repo_watch, "watched_repos", lambda: [repo])
    (repo / "README.md").unlink()
    repo_watch.digest_text()  # не должно бросить


def test_many_files_are_summarised_not_dumped(repo, monkeypatch):
    """Двадцать имён в сообщении Telegram никто не прочитает."""
    monkeypatch.setattr(repo_watch, "watched_repos", lambda: [repo])
    for i in range(20):
        f = repo / f"файл{i}.py"
        f.write_text("код", encoding="utf-8")
        _age(f, repo_watch.STALE_HOURS + 1)

    text = repo_watch.digest_text()
    assert "и ещё 15" in text
    assert text.count("файл") <= 6


# === Задание планировщика ==================================================


@pytest.mark.asyncio
async def test_tick_sends_nothing_when_clean(repo, monkeypatch):
    sent = []
    monkeypatch.setattr(repo_watch, "watched_repos", lambda: [repo])

    from backend.services import telegram_notify

    async def fake(text):
        sent.append(text)
        return True

    monkeypatch.setattr(telegram_notify, "send_message", fake)
    assert await repo_watch.tick() == 0
    assert sent == []


@pytest.mark.asyncio
async def test_tick_sends_when_stale(repo, monkeypatch):
    monkeypatch.setattr(repo_watch, "watched_repos", lambda: [repo])
    stale = repo / "забытый.py"
    stale.write_text("код", encoding="utf-8")
    _age(stale, repo_watch.STALE_HOURS + 1)

    sent = []
    from backend.services import telegram_notify

    async def fake(text):
        sent.append(text)
        return True

    monkeypatch.setattr(telegram_notify, "send_message", fake)
    assert await repo_watch.tick() == 1
    assert "забытый.py" in sent[0]
