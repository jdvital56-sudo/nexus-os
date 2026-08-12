"""Agent memory system — 4-layer architecture.

Layers (from raw to stable):
  INBOX       — raw input until processed (voice notes, transcripts)
  OPERATIONAL — working documents (calls, proposals) — "evidence"
  CANON       — methodology, templates, prices — stable reference
  MEMORY      — short facts with source + confidence — what agent trusts FIRST

Key distinction:
  DOCUMENT = agent CITES as evidence
  MEMORY   = agent TRUSTS as "what is true now"

Each memory fact has: source, confidence, TTL (time-to-live), created/updated timestamps.
"""
import json
import logging
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from ..core.config import DATA_DIR, ensure_data_dir
from ..core.errors import NotFoundError
from ..core.jsonio import read_json, write_json
from ..core import eventbus

logger = logging.getLogger(__name__)


class MemoryLayer(str, Enum):
    INBOX = "inbox"
    OPERATIONAL = "operational"
    CANON = "canonical"
    MEMORY = "memory"


class MemoryFact(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: str  # the fact itself (2-4 lines)
    layer: MemoryLayer = MemoryLayer.INBOX
    source: str = ""  # which session/document/agent created this
    confidence: float = 0.5  # 0.0 = rumor, 1.0 = verified
    ttl_hours: int | None = None  # None = never expires
    tags: list[str] = Field(default_factory=list)
    related_docs: list[str] = Field(default_factory=list)  # document IDs
    superseded_by: str | None = None  # if replaced by newer fact
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def is_expired(self) -> bool:
        if self.ttl_hours is None:
            return False
        created = datetime.fromisoformat(self.created_at)
        return datetime.utcnow() > created + timedelta(hours=self.ttl_hours)

    @property
    def is_active(self) -> bool:
        return self.superseded_by is None and not self.is_expired


MEMORY_FILE = DATA_DIR / "memory.json"

# Индексация в векторный стор — боевое поведение. В тестах выключается:
# поднимать ChromaDB на каждый факт долго, а текстовый поиск им хватает.
INDEXING_ENABLED = True

# Насколько слой ценен при вспоминании. Сырой диалог из INBOX — самый
# шумный: там лежит каждое сообщение дословно, включая сам вопрос.
LAYER_WEIGHTS = {
    MemoryLayer.INBOX: 0.4,
    MemoryLayer.OPERATIONAL: 1.0,
    MemoryLayer.CANON: 1.5,
    MemoryLayer.MEMORY: 1.5,
}


def _load() -> list[dict]:
    ensure_data_dir()
    if MEMORY_FILE.exists():
        return read_json(MEMORY_FILE, [])
    return []


def _save(facts: list[dict]):
    ensure_data_dir()
    write_json(MEMORY_FILE, facts)


def add_fact(
    content: str,
    layer: MemoryLayer = MemoryLayer.INBOX,
    source: str = "",
    confidence: float = 0.5,
    ttl_hours: int | None = None,
    tags: list[str] | None = None,
    related_docs: list[str] | None = None,
) -> MemoryFact:
    """Add a new memory fact."""
    facts = _load()
    fact = MemoryFact(
        content=content,
        layer=layer,
        source=source,
        confidence=confidence,
        ttl_hours=ttl_hours,
        tags=tags or [],
        related_docs=related_docs or [],
    )
    facts.append(fact.model_dump())
    _save(facts)

    # Индексируем здесь, а не у вызывающего: иначе факты, добавленные не
    # через диалог, оставались бы невидимыми для recall()
    _index_fact(fact)

    eventbus.emit(
        eventbus.MEMORY_FACT_ADDED,
        {
            "fact_id": fact.id,
            "layer": fact.layer.value,
            "summary": fact.content[:160],
            "source": fact.source,
        },
    )
    return fact


def _index_fact(fact: "MemoryFact") -> None:
    """Кладёт факт в векторный индекс. Молча уступает, если он недоступен."""
    if not INDEXING_ENABLED:
        return
    try:
        from .vector_store import add_vector

        text = f"[{fact.source}] {fact.content}" if fact.source else fact.content
        add_vector(
            f"memory:{fact.id}",
            text,
            {"type": "memory", "layer": fact.layer.value, "confidence": fact.confidence},
        )
    except Exception:
        logger.debug("Факт %s не проиндексирован", fact.id, exc_info=True)


def get_facts(
    layer: MemoryLayer | None = None,
    tags: list[str] | None = None,
    active_only: bool = True,
    min_confidence: float = 0.0,
    limit: int = 50,
) -> list[MemoryFact]:
    """Retrieve memory facts with filters."""
    facts = [MemoryFact(**f) for f in _load()]

    if active_only:
        facts = [f for f in facts if f.is_active]
    if layer:
        facts = [f for f in facts if f.layer == layer]
    if tags:
        tag_set = set(tags)
        facts = [f for f in facts if tag_set & set(f.tags)]
    if min_confidence > 0:
        facts = [f for f in facts if f.confidence >= min_confidence]

    # Sort: higher confidence first, then newer
    facts.sort(key=lambda f: (-f.confidence, f.created_at), reverse=False)
    return facts[:limit]


def get_fact(fact_id: str) -> MemoryFact:
    """Get a single fact by ID."""
    facts = _load()
    for f in facts:
        if f["id"] == fact_id:
            return MemoryFact(**f)
    raise NotFoundError("Memory fact", fact_id)


def update_fact(fact_id: str, **kwargs) -> MemoryFact:
    """Update a memory fact."""
    facts = _load()
    for i, f in enumerate(facts):
        if f["id"] == fact_id:
            for k, v in kwargs.items():
                if k in f and v is not None:
                    f[k] = v
            f["updated_at"] = datetime.utcnow().isoformat()
            facts[i] = f
            _save(facts)
            return MemoryFact(**f)
    raise NotFoundError("Memory fact", fact_id)


def supersede(old_id: str, new_content: str, source: str = "", confidence: float = 0.5) -> MemoryFact:
    """Replace an old fact with a new one. Old fact marked as superseded."""
    old = get_fact(old_id)

    # Create new fact in same layer
    new_fact = add_fact(
        content=new_content,
        layer=old.layer,
        source=source or old.source,
        confidence=confidence,
        ttl_hours=old.ttl_hours,
        tags=old.tags,
        related_docs=old.related_docs,
    )

    # Mark old as superseded
    update_fact(old_id, superseded_by=new_fact.id)
    return new_fact


def promote(fact_id: str, to_layer: MemoryLayer) -> MemoryFact:
    """Promote a fact to a higher layer (inbox → operational → canonical → memory)."""
    fact = get_fact(fact_id)
    layer_order = [MemoryLayer.INBOX, MemoryLayer.OPERATIONAL, MemoryLayer.CANON, MemoryLayer.MEMORY]
    current_idx = layer_order.index(fact.layer)
    target_idx = layer_order.index(to_layer)

    if target_idx <= current_idx:
        return fact  # can only promote up

    return update_fact(fact_id, layer=to_layer.value)


def demote(fact_id: str, to_layer: MemoryLayer) -> MemoryFact:
    """Demote a fact to a lower layer."""
    return update_fact(fact_id, layer=to_layer.value)


# Русское слово меняет окончание, а основа остаётся: «автопилот» и
# «автопилоту» — одно и то же. Сравнение слов целиком этого не видит, и
# вопрос «что решили по автопилоту» не находил факт про автопилот вовсе.
# Грубая обрезка до основы одинаково применяется к запросу и к факту —
# морфологический разбор здесь избыточен, а зависимость стоила бы дороже.
_STEM_LEN = 5

# Служебные слова совпадают в любых двух фразах и весят наравне со
# значимыми. Из-за этого вопрос «что решили по автопилоту» находил первым
# факт про ставку — там тоже было «по». Выбрасываем их из сравнения.
_STOP_WORDS = frozenset({
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то",
    "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за",
    "бы", "по", "только", "ее", "мне", "было", "вот", "от", "меня", "еще",
    "нет", "о", "из", "ему", "теперь", "когда", "даже", "ну", "вдруг", "ли",
    "если", "уже", "или", "ни", "быть", "был", "него", "до", "вас", "нибудь",
    "опять", "уж", "вам", "ведь", "там", "потом", "себя", "ничего", "ей",
    "они", "тут", "где", "есть", "надо", "ней", "для", "мы", "тебя", "их",
    "чем", "была", "сам", "чтоб", "без", "будто", "чего", "раз", "тоже",
    "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того", "потому",
    "этого", "какой", "совсем", "ним", "здесь", "этом", "один", "почти",
    "мой", "тем", "чтобы", "нее", "были", "куда", "зачем", "всех", "никогда",
    "можно", "при", "наконец", "два", "об", "другой", "хоть", "после", "над",
    "больше", "тот", "через", "эти", "нас", "про", "всего", "них", "какая",
    "много", "разве", "три", "эту", "моя", "впрочем", "хорошо", "свою",
    "этой", "перед", "иногда", "лучше", "чуть", "том", "нельзя", "такой",
    "им", "более", "всегда", "конечно", "всю", "между",
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
})


def _stem(word: str) -> str:
    return word[:_STEM_LEN] if len(word) > _STEM_LEN else word


def _stems(text: str) -> set[str]:
    return {_stem(w) for w in text.split() if w and w not in _STOP_WORDS}


def recall(query: str, limit: int = 5) -> list[MemoryFact]:
    """Semantic recall — find facts matching a query.

    Uses vector search when available, falls back to text search.
    """
    # Try vector search first
    try:
        from .vector_store import search_vectors
        results = search_vectors(query, limit=limit, min_score=0.3)
        if results:
            # Map vector results back to memory facts
            facts = []
            for r in results:
                if r["id"].startswith("memory:"):
                    fact_id = r["id"].replace("memory:", "")
                    try:
                        facts.append(get_fact(fact_id))
                    except NotFoundError:
                        pass
            if facts:
                return facts
    except Exception:
        pass

    # Fallback to text search
    facts = get_facts(active_only=True, limit=200)
    query_lower = query.lower()

    scored = []
    for fact in facts:
        score = 0.0
        content_lower = fact.content.lower()

        # Exact match
        if query_lower in content_lower:
            score += 1.0

        # Пересечение слов — по основам, а не по словоформам
        query_words = _stems(query_lower)
        content_words = _stems(content_lower)
        overlap = query_words & content_words
        if overlap:
            score += len(overlap) / max(len(query_words), 1)

        # Tag match
        for tag in fact.tags:
            if tag.lower() in query_lower:
                score += 0.3

        # Confidence boost
        score *= (0.5 + fact.confidence * 0.5)

        # Слой важнее совпадения слов: выводы и канон полезнее сырого диалога.
        # Без этого recall возвращал эхо самого вопроса — ведь каждое
        # сообщение лежит в INBOX дословно и совпадает с запросом лучше всего.
        score *= LAYER_WEIGHTS.get(fact.layer, 1.0)

        if score > 0:
            scored.append((score, fact))

    scored.sort(key=lambda x: -x[0])
    return [f for _, f in scored[:limit]]


def get_stats() -> dict:
    """Memory system statistics."""
    facts = [MemoryFact(**f) for f in _load()]
    active = [f for f in facts if f.is_active]
    expired = [f for f in facts if f.is_expired]
    superseded = [f for f in facts if f.superseded_by]

    by_layer = {}
    for f in active:
        by_layer[f.layer.value] = by_layer.get(f.layer.value, 0) + 1

    avg_confidence = sum(f.confidence for f in active) / max(len(active), 1)

    return {
        "total": len(facts),
        "active": len(active),
        "expired": len(expired),
        "superseded": len(superseded),
        "by_layer": by_layer,
        "avg_confidence": round(avg_confidence, 2),
    }


def ingest_from_document(doc_id: str, content: str, source: str = "") -> list[MemoryFact]:
    """Extract memory facts from a document.

    Distills content into 1-3 short facts with source tracking.
    """
    from .tagger import extract_keywords

    # Simple extraction: split into sentences, take key ones
    sentences = [s.strip() for s in content.replace("\n", " ").split(".") if len(s.strip()) > 20]

    facts = []
    for sentence in sentences[:3]:  # max 3 facts per document
        fact = add_fact(
            content=sentence,
            layer=MemoryLayer.OPERATIONAL,
            source=source or f"doc:{doc_id}",
            confidence=0.6,
            ttl_hours=720,  # 30 days
        )
        facts.append(fact)

    return facts


def cleanup_expired() -> int:
    """Remove expired facts. Returns count removed."""
    facts = _load()
    active = []
    removed = 0
    for f in facts:
        fact = MemoryFact(**f)
        if fact.is_expired and not fact.superseded_by:
            removed += 1
        else:
            active.append(f)
    _save(active)
    return removed
