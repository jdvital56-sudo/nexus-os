"""Куратор — гигиена памяти. Ничего не удаляет.

Три вида уборки, и ни один не стирает данные:
  дубли      — не удаляются, а помечаются устаревшими в пользу лучшего;
               обе формулировки остаются в памяти и доступны;
  старение   — не удаление, а понижение достоверности по возрасту; факт
               перестаёт влиять на решения, но остаётся в истории;
  мусор      — не удаление, а перенос в архив, откуда можно вернуть.

Канон и долговременная память не стареют вообще: туда попадает только то,
что человек подтвердил осознанно.
"""
import re
from datetime import datetime

from ..core.config import DATA_DIR, ensure_data_dir
from ..core.errors import NotFoundError
from ..core.jsonio import locked_update, read_json
from ..services import memory as mem_svc
from ..services.memory import MemoryLayer

ARCHIVE_FILE = DATA_DIR / "memory_archive.json"

# Достоверность никогда не опускается до нуля: ноль означал бы «этого не
# было», а мы лишь понижаем вес, а не отрицаем факт.
MIN_CONFIDENCE = 0.1

# Через сколько дней слой начинает стареть и на сколько за каждый период.
# INBOX — сырой диалог, шумит сильнее всех, поэтому стареет быстро.
DECAY_RULES = {
    MemoryLayer.INBOX: {"after_days": 7, "period_days": 7, "step": 0.1},
    MemoryLayer.OPERATIONAL: {"after_days": 30, "period_days": 30, "step": 0.05},
}

_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_SPACES = re.compile(r"\s+", flags=re.UNICODE)


def _normalize(text: str) -> str:
    """Приводит текст к виду, по которому ищем дубли."""
    return _SPACES.sub(" ", _PUNCT.sub(" ", (text or "").lower())).strip()


def _age_days(fact, now: datetime) -> float:
    try:
        created = datetime.fromisoformat(fact.created_at)
    except ValueError:
        return 0.0
    return (now - created).total_seconds() / 86400


# === Поиск: что убрать, ничего не трогая ===


def find_duplicates() -> list[dict]:
    """Группы одинаковых по смыслу фактов.

    Оставляем самый достоверный; при равной достоверности — самый ранний,
    потому что у него больше шансов быть уже связанным с графом.
    """
    groups: dict[str, list] = {}
    for fact in mem_svc.get_facts(limit=10000):
        if not fact.is_active:
            continue
        key = _normalize(fact.content)
        if not key:
            continue  # пустое — это мусор, им занимается find_junk
        groups.setdefault(key, []).append(fact)

    result = []
    for key, facts in groups.items():
        if len(facts) < 2:
            continue
        facts.sort(key=lambda f: (-f.confidence, f.created_at))
        keeper = facts[0]
        result.append({
            "keep": keeper.id,
            "drop": [f.id for f in facts[1:]],
            "content": keeper.content[:120],
            "count": len(facts),
        })
    return sorted(result, key=lambda g: -g["count"])


def find_stale(now: datetime | None = None) -> list[dict]:
    """Факты, у которых достоверность должна опуститься по возрасту."""
    now = now or datetime.utcnow()
    stale = []
    for fact in mem_svc.get_facts(limit=10000):
        if not fact.is_active:
            continue
        rule = DECAY_RULES.get(fact.layer)
        if rule is None:
            continue  # канон и долговременная память не стареют

        age = _age_days(fact, now)
        if age < rule["after_days"]:
            continue

        periods = 1 + int((age - rule["after_days"]) // rule["period_days"])
        target = round(max(MIN_CONFIDENCE, fact.confidence - rule["step"] * periods), 3)
        if target >= fact.confidence:
            continue

        stale.append({
            "id": fact.id,
            "from": fact.confidence,
            "to": target,
            "age_days": round(age, 1),
            "layer": fact.layer.value,
        })
    return sorted(stale, key=lambda s: -s["age_days"])


def find_junk() -> list[dict]:
    """Технический мусор: пустые и обрывочные записи.

    Порог намеренно жёсткий. Лучше оставить сомнительное в памяти, чем
    отправить в архив живой короткий факт.
    """
    junk = []
    for fact in mem_svc.get_facts(limit=10000):
        if not fact.is_active:
            continue
        content = (fact.content or "").strip()
        if not content:
            junk.append({"id": fact.id, "reason": "пустая запись", "content": ""})
        elif len(_normalize(content)) < 3:
            junk.append({"id": fact.id, "reason": "обрывок без смысла", "content": content[:40]})
    return junk


# === Применение: по-прежнему без удаления ===


def merge_duplicates(groups: list[dict] | None = None) -> int:
    """Помечает дубли устаревшими в пользу оставленного. Тексты сохраняются."""
    groups = groups if groups is not None else find_duplicates()
    merged = 0
    for group in groups:
        for fact_id in group["drop"]:
            try:
                mem_svc.update_fact(fact_id, superseded_by=group["keep"])
                merged += 1
            except NotFoundError:
                pass
    return merged


def apply_decay(items: list[dict] | None = None) -> int:
    """Понижает достоверность. Сам факт остаётся нетронутым."""
    items = items if items is not None else find_stale()
    changed = 0
    for item in items:
        try:
            mem_svc.update_fact(item["id"], confidence=item["to"])
            changed += 1
        except NotFoundError:
            pass
    return changed


def _load_archive() -> list[dict]:
    ensure_data_dir()
    return read_json(ARCHIVE_FILE, [])


def archive_junk(items: list[dict] | None = None) -> int:
    """Переносит мусор в архив. Оттуда его можно вернуть в любой момент.

    23.08.2026: раньше читало/писало memory.json и archive.json напрямую
    через приватные mem_svc._load/_save, без лока — тот же класс гонки,
    что нашёл внешний аудит и что уже починено в самом memory.py.
    locked_update — тот же межпроцессный лок, что у add_fact/update_fact.
    """
    items = items if items is not None else find_junk()
    ids = {i["id"] for i in items}
    if not ids:
        return 0

    moved: list[dict] = []

    def split(facts: list[dict]) -> list[dict]:
        kept = []
        for raw in facts:
            if raw["id"] in ids:
                moved.append({**raw, "archived_at": datetime.utcnow().isoformat()})
            else:
                kept.append(raw)
        return kept

    ensure_data_dir()
    locked_update(mem_svc.MEMORY_FILE, split, default=[])
    if moved:
        locked_update(ARCHIVE_FILE, lambda records: records + moved, default=[])
    return len(moved)


def list_archive() -> list[dict]:
    return _load_archive()


def restore(fact_id: str) -> dict:
    """Возвращает факт из архива обратно в память.

    Порядок нарочно такой: сперва кладём факт обратно в память, потом
    убираем его из архива — если между этими двумя шагами что-то упадёт,
    факт временно окажется в обоих местах (заметно и безопасно), а не
    пропадёт из обоих сразу.
    """
    archive = _load_archive()
    match = next((raw for raw in archive if raw["id"] == fact_id), None)
    if match is None:
        raise NotFoundError("Archived fact", fact_id)
    restored = {k: v for k, v in match.items() if k != "archived_at"}

    ensure_data_dir()
    locked_update(mem_svc.MEMORY_FILE, lambda facts: facts + [restored], default=[])
    locked_update(ARCHIVE_FILE, lambda records: [r for r in records if r["id"] != fact_id], default=[])
    return restored


# === Полный проход ===


def run_cycle(apply: bool = False, now: datetime | None = None) -> dict:
    """Осмотр памяти. По умолчанию только смотрит и составляет отчёт.

    Уборка происходит лишь при apply=True — чтобы человек сначала увидел,
    что именно собираются тронуть.
    """
    duplicates = find_duplicates()
    stale = find_stale(now=now)
    junk = find_junk()

    report = {
        "applied": apply,
        "duplicates": {"groups": len(duplicates), "facts": sum(len(g["drop"]) for g in duplicates)},
        "decay": {"facts": len(stale)},
        "junk": {"facts": len(junk)},
        "details": {"duplicates": duplicates[:20], "decay": stale[:20], "junk": junk[:20]},
    }

    if apply:
        report["duplicates"]["merged"] = merge_duplicates(duplicates)
        report["decay"]["changed"] = apply_decay(stale)
        report["junk"]["archived"] = archive_junk(junk)

    return report


def get_stats() -> dict:
    mem_stats = mem_svc.get_stats()
    return {
        "memory": mem_stats,
        "archived": len(_load_archive()),
        "duplicate_groups": len(find_duplicates()),
        "stale_facts": len(find_stale()),
        "junk_facts": len(find_junk()),
    }
