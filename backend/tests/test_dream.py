"""Тесты Dream Cadence: находки, статусы, гигиена памяти (PR-11)."""
import json

import pytest

from backend.agents.dream_cadence import DreamCadence
from backend.services import budget
from backend.services import dream as store
from backend.services import memory as mem_svc
from backend.services.memory import MemoryLayer


class ScriptedLLM:
    """Отвечает заранее заданным JSON и помнит вид вызова."""

    def __init__(self, payload):
        self.payload = payload
        self.kinds: list[str] = []

    async def generate_response(self, prompt: str, context: str = "", kind: str = "interactive", json_mode: bool = False) -> str:
        self.kinds.append(kind)
        if callable(self.payload):
            return self.payload(prompt)
        return json.dumps(self.payload, ensure_ascii=False)


# --- Хранилище находок ---


def test_finding_starts_as_new():
    f = store.add_finding("run-1", "Cost Intelligence", "Расходы выросли втрое")

    assert f["status"] == store.STATUS_NEW
    assert f["finding_id"]
    assert f["severity"] == "medium"


def test_invalid_severity_falls_back():
    f = store.add_finding("run-1", "Skill Performance", "x", severity="катастрофа")
    assert f["severity"] == "medium"


def test_findings_can_be_filtered():
    store.add_finding("run-1", "A", "первая")
    store.add_finding("run-2", "B", "вторая")

    assert len(store.list_findings(run_id="run-1")) == 1
    assert len(store.list_findings()) == 2


def test_skip_marks_finding_resolved():
    f = store.add_finding("run-1", "A", "не нужно")

    skipped = store.skip(f["finding_id"])

    assert skipped["status"] == store.STATUS_SKIPPED
    assert skipped["resolved_at"]


def test_apply_promotes_fact_only_on_demand():
    """Продвижение в OPERATIONAL — только по решению человека (I-2)."""
    fact = mem_svc.add_fact("Клиент просил счёт до пятницы", layer=MemoryLayer.INBOX)
    finding = store.add_finding(
        "run-1", "Memory Hygiene", "Продвинуть факт",
        action={"type": "promote_fact", "fact_id": fact.id, "to_layer": "operational"},
    )

    # До Apply факт остаётся в карантине
    assert mem_svc.get_fact(fact.id).layer == MemoryLayer.INBOX

    store.apply(finding["finding_id"])

    assert mem_svc.get_fact(fact.id).layer == MemoryLayer.OPERATIONAL
    assert store.get_finding(finding["finding_id"])["status"] == store.STATUS_APPLIED


def test_apply_is_idempotent():
    fact = mem_svc.add_fact("Факт", layer=MemoryLayer.INBOX)
    f = store.add_finding(
        "run-1", "Memory Hygiene", "Продвинуть",
        action={"type": "promote_fact", "fact_id": fact.id, "to_layer": "operational"},
    )
    store.apply(f["finding_id"])
    store.apply(f["finding_id"])  # повторный вызов ничего не ломает

    assert store.get_finding(f["finding_id"])["status"] == store.STATUS_APPLIED


def test_finding_without_action_just_changes_status():
    f = store.add_finding("run-1", "Cost Intelligence", "Просто наблюдение")
    assert store.apply(f["finding_id"])["status"] == store.STATUS_APPLIED


# --- Прогон ---


@pytest.mark.asyncio
async def test_analysis_is_a_background_call():
    """Ночной прогон — фон, его обязан глушить бюджет (I-4)."""
    mem_svc.add_fact("что-то", tags=["dialog"])
    llm = ScriptedLLM({"findings": [{"title": "Находка", "severity": "high"}]})
    dc = DreamCadence(llm=llm)

    await dc.analyze_dimension("run-x", "Conversation & Context Drift")

    assert llm.kinds == [budget.BACKGROUND]


@pytest.mark.asyncio
async def test_dimension_without_data_is_skipped():
    """Пустых данных нет — значит и выдумывать нечего."""
    llm = ScriptedLLM({"findings": [{"title": "Выдумка"}]})
    dc = DreamCadence(llm=llm)

    result = await dc.analyze_dimension("run-x", "Business Outcomes")

    assert result == []
    assert llm.kinds == []  # модель даже не звалась


@pytest.mark.asyncio
async def test_memory_hygiene_processes_inbox():
    """Гигиена памяти обязана реально разбирать INBOX (I-2)."""
    keep = mem_svc.add_fact("Клиент платит 500$ в месяц", layer=MemoryLayer.INBOX)
    noise = mem_svc.add_fact("привет как дела", layer=MemoryLayer.INBOX)

    llm = ScriptedLLM({
        "promote": [{"fact_id": keep.id, "reason": "коммерческий факт"}],
        "noise": [{"fact_id": noise.id, "reason": "болтовня"}],
    })
    dc = DreamCadence(llm=llm)

    findings = await dc.analyze_memory_hygiene("run-x")

    promote = [f for f in findings if (f.get("action") or {}).get("type") == "promote_fact"]
    assert len(promote) == 1
    assert promote[0]["action"]["fact_id"] == keep.id
    # Само по себе продвижение НЕ произошло — только предложение
    assert mem_svc.get_fact(keep.id).layer == MemoryLayer.INBOX


@pytest.mark.asyncio
async def test_hygiene_ignores_invented_fact_ids():
    """Модель может выдумать id — такие предложения отбрасываем."""
    mem_svc.add_fact("реальный", layer=MemoryLayer.INBOX)
    llm = ScriptedLLM({"promote": [{"fact_id": "выдуманный", "reason": "?"}], "noise": []})
    dc = DreamCadence(llm=llm)

    assert await dc.analyze_memory_hygiene("run-x") == []


@pytest.mark.asyncio
async def test_empty_inbox_needs_no_hygiene():
    llm = ScriptedLLM({"promote": [], "noise": []})
    dc = DreamCadence(llm=llm)

    assert await dc.analyze_memory_hygiene("run-x") == []
    assert llm.kinds == []


@pytest.mark.asyncio
async def test_full_run_records_findings_and_brief():
    mem_svc.add_fact("Диалог о клиенте", tags=["dialog"])
    llm = ScriptedLLM({"findings": [{"title": "Требует внимания", "severity": "high"}]})
    dc = DreamCadence(llm=llm)

    run = await dc.run_full_analysis()
    await dc.generate_morning_brief(run)

    assert run["findings"]
    cached = store.get_brief()
    assert cached["run_id"] == run["run_id"]
    assert cached["findings_count"] == len(run["findings"])


@pytest.mark.asyncio
async def test_exhausted_budget_stops_the_run(monkeypatch):
    from backend.core.config import settings

    mem_svc.add_fact("Диалог", tags=["dialog"])
    monkeypatch.setattr(settings, "daily_llm_budget_usd", 0.0)
    monkeypatch.setattr(budget, "spent_today", lambda: 1.0)
    dc = DreamCadence(llm=ScriptedLLM({"findings": []}))

    run = await dc.run_full_analysis()

    assert run["findings"] == []


@pytest.mark.asyncio
async def test_brief_without_findings_is_honest():
    dc = DreamCadence(llm=ScriptedLLM({"findings": []}))

    brief = await dc.generate_morning_brief({"run_id": "run-x", "findings": [], "cost_usd": 0.0})

    assert "без находок" in brief


# --- HTTP API ---


def test_api_lists_and_resolves_findings(client):
    f = store.add_finding("run-1", "Cost Intelligence", "Проверить расходы")

    assert client.get("/api/dream/findings").status_code == 200
    assert client.post(f"/api/dream/findings/{f['finding_id']}/skip").json()["status"] == "skipped"


def test_api_filters_by_status(client):
    a = store.add_finding("run-1", "A", "первая")
    store.add_finding("run-1", "B", "вторая")
    client.post(f"/api/dream/findings/{a['finding_id']}/skip")

    new_ones = client.get("/api/dream/findings", params={"status": "new"}).json()

    assert [f["title"] for f in new_ones] == ["вторая"]


def test_api_brief_is_404_before_first_run(client):
    assert client.get("/api/dream/brief").status_code == 404


def test_api_brief_reads_cache(client):
    store.save_brief("run-7", "Всё спокойно", cost_usd=0.01, findings_count=0)

    body = client.get("/api/dream/brief").json()

    assert body["run_id"] == "run-7"
    assert body["brief"] == "Всё спокойно"
