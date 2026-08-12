"""Тесты Куратора. Главный инвариант: ни один факт не пропадает бесследно."""
from datetime import datetime, timedelta

import pytest

from backend.core.errors import NotFoundError
from backend.services import curator as svc
from backend.services import memory as mem_svc
from backend.services.memory import MemoryLayer


def _add(content="факт", layer=MemoryLayer.OPERATIONAL, confidence=0.5, days_ago=0):
    fact = mem_svc.add_fact(content=content, layer=layer, confidence=confidence)
    if days_ago:
        old = (datetime.utcnow() - timedelta(days=days_ago)).isoformat()
        raw = mem_svc._load()
        for r in raw:
            if r["id"] == fact.id:
                r["created_at"] = old
        mem_svc._save(raw)
    return fact


def _active_ids():
    return {f.id for f in mem_svc.get_facts(limit=1000) if f.is_active}


# === Дубли ===


def test_finds_duplicates_ignoring_case_and_punctuation():
    _add("Клиент платит картой")
    _add("клиент платит картой!!!")
    groups = svc.find_duplicates()
    assert len(groups) == 1
    assert groups[0]["count"] == 2


def test_different_facts_are_not_duplicates():
    _add("Клиент платит картой")
    _add("Клиент платит наличными")
    assert svc.find_duplicates() == []


def test_keeps_the_most_trusted_copy():
    weak = _add("одно и то же", confidence=0.3)
    strong = _add("Одно И То Же", confidence=0.9)
    group = svc.find_duplicates()[0]
    assert group["keep"] == strong.id
    assert group["drop"] == [weak.id]


def test_merge_does_not_delete_anything():
    _add("повтор", confidence=0.3)
    _add("повтор", confidence=0.9)
    before = len(mem_svc._load())

    assert svc.merge_duplicates() == 1

    assert len(mem_svc._load()) == before, "склейка не должна удалять записи"
    assert len(_active_ids()) == 1, "в активной памяти остаётся один"


def test_merged_copy_keeps_its_text_and_points_to_keeper():
    weak = _add("повтор", confidence=0.3)
    strong = _add("повтор", confidence=0.9)
    svc.merge_duplicates()

    dropped = mem_svc.get_fact(weak.id)
    assert dropped.content == "повтор", "текст обеих формулировок сохраняется"
    assert dropped.superseded_by == strong.id


def test_merge_is_idempotent():
    _add("повтор", confidence=0.3)
    _add("повтор", confidence=0.9)
    svc.merge_duplicates()
    assert svc.merge_duplicates() == 0


# === Старение ===


def test_fresh_facts_do_not_decay():
    _add(layer=MemoryLayer.INBOX, days_ago=1)
    assert svc.find_stale() == []


def test_inbox_decays_after_a_week():
    fact = _add(layer=MemoryLayer.INBOX, confidence=0.5, days_ago=8)
    stale = svc.find_stale()
    assert len(stale) == 1
    assert stale[0]["id"] == fact.id
    assert stale[0]["to"] < 0.5


def test_older_facts_decay_further():
    _add("свежий", layer=MemoryLayer.INBOX, confidence=0.9, days_ago=8)
    _add("древний", layer=MemoryLayer.INBOX, confidence=0.9, days_ago=60)
    by_age = {s["age_days"]: s["to"] for s in svc.find_stale()}
    young, old = min(by_age), max(by_age)
    assert by_age[old] < by_age[young]


@pytest.mark.parametrize("layer", [MemoryLayer.CANON, MemoryLayer.MEMORY])
def test_canon_never_decays(layer):
    """Канон человек подтвердил осознанно — возраст его не обесценивает."""
    _add(layer=layer, days_ago=500)
    assert svc.find_stale() == []


def test_confidence_never_reaches_zero():
    fact = _add(layer=MemoryLayer.INBOX, confidence=0.5, days_ago=3650)
    svc.apply_decay()
    assert mem_svc.get_fact(fact.id).confidence == svc.MIN_CONFIDENCE


def test_decay_changes_only_confidence():
    fact = _add("важный текст", layer=MemoryLayer.INBOX, confidence=0.8, days_ago=30)
    svc.apply_decay()
    after = mem_svc.get_fact(fact.id)
    assert after.content == "важный текст"
    assert after.is_active
    assert after.confidence < 0.8


# === Мусор и архив ===


def test_finds_empty_and_broken_records():
    empty = _add("   ")
    broken = _add("!!")
    good = _add("нормальный факт")
    junk_ids = {j["id"] for j in svc.find_junk()}
    assert junk_ids == {empty.id, broken.id}
    assert good.id not in junk_ids


def test_short_but_meaningful_fact_survives():
    """Порог жёсткий: лучше оставить сомнительное, чем убрать живое."""
    _add("SEO")
    assert svc.find_junk() == []


def test_archive_moves_out_of_memory_but_keeps_the_record():
    junk = _add("  ")
    _add("нормальный факт")

    assert svc.archive_junk() == 1

    with pytest.raises(NotFoundError):
        mem_svc.get_fact(junk.id)
    assert [r["id"] for r in svc.list_archive()] == [junk.id]


def test_restore_brings_it_back():
    junk = _add("  ")
    svc.archive_junk()

    svc.restore(junk.id)

    assert mem_svc.get_fact(junk.id).id == junk.id
    assert svc.list_archive() == []


def test_restore_of_unknown_id_raises():
    with pytest.raises(NotFoundError):
        svc.restore("нет-такого")


def test_archive_survives_reload_with_cyrillic(temp_data_dir):
    _add(" ")
    svc.archive_junk()
    raw = (temp_data_dir / "memory_archive.json").read_text(encoding="utf-8")
    assert "archived_at" in raw


# === Полный проход ===


def test_inspect_changes_nothing():
    _add("повтор", confidence=0.3)
    _add("повтор", confidence=0.9)
    _add(layer=MemoryLayer.INBOX, days_ago=40)
    before = mem_svc._load()

    report = svc.run_cycle(apply=False)

    assert report["applied"] is False
    assert report["duplicates"]["facts"] == 1
    assert mem_svc._load() == before, "осмотр не должен ничего менять"


def test_apply_does_the_work():
    _add("повтор", confidence=0.3)
    _add("повтор", confidence=0.9)
    _add("устарел", layer=MemoryLayer.INBOX, days_ago=40)
    _add("  ")

    report = svc.run_cycle(apply=True)

    assert report["applied"] is True
    assert report["duplicates"]["merged"] == 1
    assert report["decay"]["changed"] >= 1
    assert report["junk"]["archived"] == 1


def test_nothing_to_do_on_clean_memory():
    _add("единственный осмысленный факт")
    report = svc.run_cycle(apply=True)
    assert report["duplicates"]["facts"] == 0
    assert report["junk"]["facts"] == 0


def test_stats():
    _add("повтор", confidence=0.3)
    _add("повтор", confidence=0.9)
    stats = svc.get_stats()
    assert stats["duplicate_groups"] == 1
    assert stats["archived"] == 0


# === Агент ===


def test_curator_agent_cycle_runs():
    from backend.models.schemas import AgentRole
    from backend.services.agent_engine import ROLE_CYCLES

    assert AgentRole.CURATOR in ROLE_CYCLES


def test_curator_agent_never_reports_deletions():
    from backend.models.schemas import Agent, AgentRole, AgentStatus
    from backend.services import agent_engine

    _add("повтор", confidence=0.3)
    _add("повтор", confidence=0.9)
    _add("  ")

    agent = Agent(id="cur", name="Куратор", role=AgentRole.CURATOR, status=AgentStatus.IDLE)
    verify = agent_engine.execute_cycle(agent, "уборка памяти")["result"]["verify"]

    assert verify["deleted"] == 0
    assert verify["merged"] == 1


def test_curator_agent_asks_before_archiving():
    """Архивация вынимает записи из памяти — только через задачу человеку."""
    from backend.models.schemas import Agent, AgentRole, AgentStatus
    from backend.services import agent_engine
    from backend.services import tasks as task_svc

    junk = _add("  ")
    agent = Agent(id="cur", name="Куратор", role=AgentRole.CURATOR, status=AgentStatus.IDLE)
    agent_engine.execute_cycle(agent, "уборка памяти")

    assert mem_svc.get_fact(junk.id).id == junk.id, "агент не архивирует сам"
    assert any("Архивировать" in t.title for t in task_svc.list_tasks())


# === API ===


def test_api_inspect_and_run(client):
    _add("повтор", confidence=0.3)
    _add("повтор", confidence=0.9)

    inspect = client.get("/api/curator/inspect")
    assert inspect.status_code == 200
    assert inspect.json()["applied"] is False

    run = client.post("/api/curator/run?apply=true")
    assert run.json()["duplicates"]["merged"] == 1


def test_api_archive_and_restore(client):
    junk = _add("  ")
    client.post("/api/curator/run?apply=true")

    assert len(client.get("/api/curator/archive").json()) == 1

    restored = client.post(f"/api/curator/restore/{junk.id}")
    assert restored.status_code == 200
    assert client.get("/api/curator/archive").json() == []


def test_api_stats(client):
    assert client.get("/api/curator/stats").status_code == 200
