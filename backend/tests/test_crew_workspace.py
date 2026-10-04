"""Границы песочницы и протокол передачи.

Таблицы «что должно теперь работать» и «что должно ПО-ПРЕЖНЕМУ не работать»
идут в одном файле сознательно. У этого проекта уже был случай, когда порог
чинили под жалобу дня и ломали то, что он защищал раньше; проверка обеих
сторон в одной таблице — единственное, что от этого спасает.
"""
from __future__ import annotations

import concurrent.futures
import os

import pytest

from crew import config, handoff
from crew.workspace import Workspace, WorkspaceError


@pytest.fixture(autouse=True)
def crew_root(tmp_path, monkeypatch):
    """Каждый тест — своя пустая файловая система ролей."""
    monkeypatch.setattr(config, "CREW_ROOT", tmp_path / "crew")
    config.ensure_layout()
    return tmp_path / "crew"


# --- что должно работать ---------------------------------------------------

@pytest.mark.parametrize(
    "relative",
    [
        "docs/research/monsheri/analysis.md",
        "./docs/notes.md",
        "docs/deep/nested/path/file.md",
    ],
)
def test_write_inside_workspace_is_allowed(relative):
    ws = Workspace("marketer")
    shown = ws.write(relative, "содержимое")
    assert ws.read(relative) == "содержимое"
    assert not shown.startswith("/"), "путь показываем относительным"


def test_absolute_path_inside_own_workspace_is_allowed():
    """Модель, насмотревшись на свои прошлые ответы, пишет полный путь."""
    ws = Workspace("marketer")
    ws.write("docs/a.md", "x")
    absolute = str(config.workspace_of("marketer") / "docs" / "a.md")
    assert ws.read(absolute) == "x"


def test_patch_replaces_single_occurrence():
    ws = Workspace("screenwriter")
    ws.write("docs/idea.md", "кадр 1\nкадр 2\nкадр 3\n")
    ws.patch("docs/idea.md", "кадр 2", "кадр 2 — переснять")
    assert "кадр 2 — переснять" in ws.read("docs/idea.md")


def test_search_and_grep_find_by_slug():
    ws = Workspace("marketer")
    ws.write("docs/research/monsheri/analysis.md", "Бренд Monsheri, средний чек")
    assert ws.search("*monsheri*")
    assert ws.grep("средний чек")


def test_handoff_copies_files_into_recipient_inbox():
    sender = Workspace("marketer")
    sender.write("docs/research/monsheri/analysis.md", "полный анализ")
    sender.write("docs/research/monsheri/competitors.md", "конкуренты")

    record = handoff.submit(
        from_role="marketer",
        to_role="screenwriter",
        project="Monsheri",
        summary="Анализ бренда и конкурентов",
        request="Собери 3 идеи ролика",
        main_file="docs/research/monsheri/analysis.md",
        attachments=["docs/research/monsheri/competitors.md"],
    )

    assert record.project == "monsheri"
    receiver = Workspace("screenwriter")
    body = receiver.read(f"docs/inbox/handoffs/{record.handoff_id}/files/analysis.md")
    assert body == "полный анализ"
    assert len(handoff.pending("screenwriter")) == 1


def test_handoff_survives_sender_rewriting_its_file():
    """Передача самодостаточна: отправитель волен переписать свой файл."""
    sender = Workspace("marketer")
    sender.write("docs/a.md", "версия 1")
    record = handoff.submit(
        from_role="marketer", to_role="screenwriter", project="p",
        summary="s", request="r", main_file="docs/a.md",
    )
    sender.write("docs/a.md", "версия 2")

    receiver = Workspace("screenwriter")
    copied = receiver.read(f"docs/inbox/handoffs/{record.handoff_id}/files/a.md")
    assert copied == "версия 1"


def test_accept_moves_handoff_out_of_pending():
    sender = Workspace("marketer")
    sender.write("docs/a.md", "x")
    record = handoff.submit(
        from_role="marketer", to_role="screenwriter", project="p",
        summary="s", request="r", main_file="docs/a.md",
    )
    handoff.accept("screenwriter", record.handoff_id)
    assert handoff.pending("screenwriter") == []


def test_slugify_handles_russian_brand_names():
    assert handoff.slugify("Точка опоры") == "tochka-opory"
    assert handoff.slugify("Monsheri") == "monsheri"


# --- что должно ПО-ПРЕЖНЕМУ не работать ------------------------------------

@pytest.mark.parametrize(
    "escape",
    [
        "../../../../etc/passwd",
        "..",
        "docs/../../outside.md",
        "C:/Windows/System32/drivers/etc/hosts",
        "/etc/passwd",
        "~/.ssh/id_rsa",
        "docs/../../../.env",
    ],
)
def test_paths_outside_workspace_are_refused(escape):
    ws = Workspace("marketer")
    with pytest.raises(WorkspaceError):
        ws.resolve(escape)


def test_other_roles_workspace_is_outside():
    """Изоляция ролей — не декларация: Маркетолог не читает папку Сценариста."""
    other = Workspace("screenwriter")
    other.write("docs/secret.md", "чужое")
    marketer = Workspace("marketer")
    foreign = str(config.workspace_of("screenwriter") / "docs" / "secret.md")
    with pytest.raises(WorkspaceError):
        marketer.read(foreign)


@pytest.mark.parametrize("name", [".env", "credentials.json", "docs/key.pem"])
def test_secret_files_are_refused_even_inside_workspace(name):
    ws = Workspace("producer")
    with pytest.raises(WorkspaceError):
        ws.resolve(name)


def test_write_over_size_limit_is_refused():
    ws = Workspace("producer")
    with pytest.raises(WorkspaceError):
        ws.write("docs/big.md", "x" * 2_000_000)


def test_patch_refuses_ambiguous_fragment():
    ws = Workspace("screenwriter")
    ws.write("docs/a.md", "кадр\nкадр\n")
    with pytest.raises(WorkspaceError, match="2 раз"):
        ws.patch("docs/a.md", "кадр", "сцена")


def test_patch_refuses_missing_fragment():
    ws = Workspace("screenwriter")
    ws.write("docs/a.md", "кадр 1")
    with pytest.raises(WorkspaceError):
        ws.patch("docs/a.md", "кадр 9", "сцена")


def test_handoff_refuses_route_not_in_role_graph():
    """Маркетолог не передаёт напрямую Промпт-инженеру — только Сценаристу."""
    sender = Workspace("marketer")
    sender.write("docs/a.md", "x")
    with pytest.raises(handoff.HandoffError):
        handoff.submit(
            from_role="marketer", to_role="prompt_engineer", project="p",
            summary="s", request="r", main_file="docs/a.md",
        )


def test_handoff_refuses_file_outside_sender_workspace():
    Workspace("marketer")
    with pytest.raises(handoff.HandoffError):
        handoff.submit(
            from_role="marketer", to_role="screenwriter", project="p",
            summary="s", request="r", main_file="/etc/passwd",
        )


def test_double_accept_is_refused_not_silently_ignored():
    sender = Workspace("marketer")
    sender.write("docs/a.md", "x")
    record = handoff.submit(
        from_role="marketer", to_role="screenwriter", project="p",
        summary="s", request="r", main_file="docs/a.md",
    )
    handoff.accept("screenwriter", record.handoff_id)
    with pytest.raises(handoff.HandoffError):
        handoff.accept("screenwriter", record.handoff_id)


# --- дыры, найденные аудитом безопасности ---------------------------------

@pytest.mark.parametrize(
    "escape_glob",
    [
        "*/../../../producer/workspace/docs/*",
        "../*/workspace/docs/*",
        "docs/../../../*",
        "/etc/*",
        "C:/Users/*",
    ],
)
def test_glob_cannot_escape_the_workspace(escape_glob):
    """Аудит нашёл рабочий эксплойт: `..` в глобе честно проходит через
    `Path.glob`, и Маркетолог перечислял файлы Продюсера. Прочитать их было
    нельзя, но имена, структура чужих проектов и полный путь с именем
    пользователя уже уходили в модель."""
    other = Workspace("producer")
    other.write("docs/secret.md", "чужое")
    marketer = Workspace("marketer")
    marketer.write("docs/own.md", "своё")

    try:
        found = marketer.search(escape_glob)
    except WorkspaceError:
        return  # отвергнут на входе — это верный исход
    assert not any("producer" in path for path in found), (
        f"глоб {escape_glob} вывел за песочницу: {found}"
    )


def test_grep_does_not_read_denied_files():
    """`.git/config` с токеном находился поиском по содержимому, хотя
    `read_file` его не отдавал: grep проверял только имя файла."""
    ws = Workspace("marketer")
    (ws.root / ".git").mkdir(parents=True, exist_ok=True)
    (ws.root / ".git" / "config").write_text(
        "url = https://user:TOKEN123@github.com/x.git", encoding="utf-8"
    )
    (ws.root / "id.pem").write_text("-----BEGIN PRIVATE KEY----- SECRET", encoding="utf-8")
    ws.write("docs/ok.md", "обычный текст TOKEN123 SECRET")

    for needle in ("TOKEN123", "SECRET"):
        hits = ws.grep(needle, glob="**/*")
        assert not any(".git" in hit or ".pem" in hit for hit in hits), (
            f"поиск по «{needle}» вернул закрытый файл: {hits}"
        )


def test_grep_still_finds_normal_files():
    """Обратная сторона той же правки: обычный поиск не должен сломаться."""
    ws = Workspace("marketer")
    ws.write("docs/research/monsheri/analysis.md", "средний чек 15000")
    assert ws.grep("средний чек", glob="**/*")


def test_search_still_works_for_normal_patterns():
    ws = Workspace("marketer")
    ws.write("docs/research/monsheri/analysis.md", "x")
    assert ws.search("*monsheri*")
    assert ws.search("docs/**/*.md")


def test_list_files_survives_names_with_double_spaces():
    """Разбор строки списка обратно ломался на именах с двумя пробелами."""
    ws = Workspace("screenwriter")
    ws.write("docs/pack/странный  файл.md", "тело")
    assert "странный  файл.md" in ws.list_files("docs/pack")


def test_list_files_hides_denied_files():
    ws = Workspace("producer")
    ws.write("docs/pack/ok.md", "x")
    (ws.root / "docs" / "pack" / "id.pem").write_text("secret", encoding="utf-8")
    assert ws.list_files("docs/pack") == ["ok.md"]


# --- гонки -----------------------------------------------------------------

def test_concurrent_handoffs_do_not_collide():
    """Двадцать передач одновременно. Ни одна не теряется и не бьёт другую.

    Именно здесь у проекта уже болело: общий JSON, два писателя, битый файл.
    В этом протоколе общего изменяемого файла нет вовсе — проверяем, что это
    так и осталось.
    """
    sender = Workspace("marketer")
    for index in range(20):
        sender.write(f"docs/a{index}.md", f"файл {index}")

    def submit(index: int):
        return handoff.submit(
            from_role="marketer", to_role="screenwriter", project="p",
            summary=f"s{index}", request="r", main_file=f"docs/a{index}.md",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(submit, range(20)))

    assert len({r.handoff_id for r in records}) == 20
    assert len(handoff.pending("screenwriter")) == 20

    receiver = Workspace("screenwriter")
    for index, record in enumerate(records):
        body = receiver.read(f"docs/inbox/handoffs/{record.handoff_id}/files/a{index}.md")
        assert body == f"файл {index}"


def test_concurrent_writes_to_same_file_never_leave_partial_content():
    """Атомарная запись: читатель видит либо старое целиком, либо новое целиком."""
    ws = Workspace("producer")
    ws.write("docs/state.md", "A" * 50_000)

    def writer(index: int):
        ws.write("docs/state.md", ("B" if index % 2 else "C") * 50_000)

    def reader(_):
        text = ws.read("docs/state.md")
        assert len(set(text)) == 1, "в файле смесь символов — запись не атомарна"
        assert len(text) == 50_000

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(writer, range(15)))
        list(pool.map(reader, range(15)))


# --- канон имён ------------------------------------------------------------

def test_no_name_collision_with_existing_agent_roles():
    """Четырнадцать имён, все разные.

    Канон `nexus-os-naming-canon` писался после того, как одним набором имён
    назвали две сущности и получили двух «Ра». Проверка автоматическая, потому
    что на глаз её уже один раз не прошли.
    """
    from backend.models.schemas import AgentRole

    existing = {role.value for role in AgentRole}
    new = {role.key for role in config.ROLES}
    assert not (existing & new), f"ключи пересекаются: {existing & new}"

    titles = [role.title for role in config.ROLES]
    assert len(titles) == len(set(titles)), "две роли названы одинаково"

    forbidden = {"Аналитик", "Разведчик", "Исследователь"}
    assert not (set(titles) & forbidden), (
        "имя размывается с существующим «Исследователем» — см. канон имён"
    )


def test_every_role_has_a_prompt_file():
    from pathlib import Path

    roles_dir = Path(__file__).resolve().parents[2] / "crew" / "roles"
    for role in config.ROLES:
        assert (roles_dir / f"{role.key}.md").exists(), f"нет промпта для {role.title}"


def test_every_declared_reference_exists():
    """Опечатка в имени справочника иначе всплыла бы только на живом ответе бота."""
    from pathlib import Path

    roles_dir = Path(__file__).resolve().parents[2] / "crew" / "roles"
    for role in config.ROLES:
        for name in role.references:
            assert (roles_dir / name).exists(), f"{role.title}: нет справочника {name}"


def test_handoff_graph_is_consistent_in_both_directions():
    """Если А передаёт Б, то Б обязана принимать от А. Иначе тупик в рантайме."""
    for role in config.ROLES:
        for target_key in role.hands_to:
            target = config.get_role(target_key)
            assert role.key in target.accepts_from, (
                f"{role.title} передаёт {target.title}, "
                f"но {target.title} не принимает от {role.title}"
            )
        for source_key in role.accepts_from:
            source = config.get_role(source_key)
            assert role.key in source.hands_to, (
                f"{role.title} принимает от {source.title}, "
                f"но {source.title} не передаёт {role.title}"
            )
