"""Находки Dream Cadence: хранение, статусы и применение.

Ночной прогон не имеет права молча менять память (I-2): он лишь предлагает.
Каждая находка получает id и статус, человек нажимает Apply или Skip —
только после этого что-то происходит с данными.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from ..core.config import DATA_DIR, ensure_data_dir
from ..core.errors import NotFoundError
from ..core.jsonio import read_json, write_json

logger = logging.getLogger(__name__)

FINDINGS_FILE = DATA_DIR / "dream_findings.json"
BRIEF_FILE = DATA_DIR / "dream_brief.json"

STATUS_NEW = "new"
STATUS_APPLIED = "applied"
STATUS_SKIPPED = "skipped"

SEVERITIES = ("low", "medium", "high")

# Сколько прогонов держим в файле
_MAX_RUNS_KEPT = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> list[dict]:
    ensure_data_dir()
    return read_json(FINDINGS_FILE, []) or []


def _save(findings: list[dict]) -> None:
    ensure_data_dir()
    write_json(FINDINGS_FILE, findings)


def new_run_id() -> str:
    return f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"


def add_finding(
    run_id: str,
    dimension: str,
    title: str,
    detail: str = "",
    severity: str = "medium",
    action: dict[str, Any] | None = None,
) -> dict:
    """Записать находку со статусом new."""
    finding = {
        "finding_id": str(uuid.uuid4())[:8],
        "run_id": run_id,
        "dimension": dimension,
        "severity": severity if severity in SEVERITIES else "medium",
        "title": title[:200],
        "detail": detail,
        "action": action,
        "status": STATUS_NEW,
        "created_at": _now(),
        "resolved_at": None,
    }
    findings = _load()
    findings.append(finding)

    # Подрезаем историю: держим находки последних прогонов
    runs = []
    for f in findings:
        if f["run_id"] not in runs:
            runs.append(f["run_id"])
    if len(runs) > _MAX_RUNS_KEPT:
        keep = set(runs[-_MAX_RUNS_KEPT:])
        findings = [f for f in findings if f["run_id"] in keep]

    _save(findings)
    return finding


def list_findings(status: str | None = None, run_id: str | None = None, limit: int = 100) -> list[dict]:
    findings = _load()
    if status:
        findings = [f for f in findings if f["status"] == status]
    if run_id:
        findings = [f for f in findings if f["run_id"] == run_id]
    findings.sort(key=lambda f: f["created_at"], reverse=True)
    return findings[:limit]


def get_finding(finding_id: str) -> dict:
    for f in _load():
        if f["finding_id"] == finding_id:
            return f
    raise NotFoundError("Finding", finding_id)


def _set_status(finding_id: str, status: str) -> dict:
    findings = _load()
    for f in findings:
        if f["finding_id"] == finding_id:
            f["status"] = status
            f["resolved_at"] = _now()
            _save(findings)
            return f
    raise NotFoundError("Finding", finding_id)


def skip(finding_id: str) -> dict:
    """Человек решил не применять находку."""
    return _set_status(finding_id, STATUS_SKIPPED)


def apply(finding_id: str) -> dict:
    """Применить действие находки. Только по явному решению человека (I-2)."""
    finding = get_finding(finding_id)
    if finding["status"] != STATUS_NEW:
        return finding

    action = finding.get("action") or {}
    kind = action.get("type")

    if kind == "promote_fact":
        from . import memory as memory_svc

        memory_svc.promote(action["fact_id"], memory_svc.MemoryLayer(action["to_layer"]))
        logger.info("Факт %s продвинут в %s", action["fact_id"], action["to_layer"])
    elif kind == "supersede_fact":
        from . import memory as memory_svc

        memory_svc.supersede(action["fact_id"], action["content"], source="dream")
        logger.info("Факт %s заменён по решению человека", action["fact_id"])
    elif kind:
        logger.warning("Неизвестное действие находки: %s", kind)

    return _set_status(finding_id, STATUS_APPLIED)


# --- Кэш утреннего брифа ---


def save_brief(run_id: str, brief: str, cost_usd: float, findings_count: int) -> dict:
    """Ночной прогон пишет бриф, /brief читает — без синхронного анализа (R-10)."""
    payload = {
        "run_id": run_id,
        "brief": brief,
        "cost_usd": round(cost_usd, 6),
        "findings_count": findings_count,
        "created_at": _now(),
    }
    ensure_data_dir()
    write_json(BRIEF_FILE, payload)
    return payload


def get_brief() -> dict | None:
    ensure_data_dir()
    return read_json(BRIEF_FILE, None)
