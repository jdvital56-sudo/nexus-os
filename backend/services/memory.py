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
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from ..core.config import DATA_DIR, ensure_data_dir


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


def _load() -> list[dict]:
    ensure_data_dir()
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text())
    return []


def _save(facts: list[dict]):
    ensure_data_dir()
    MEMORY_FILE.write_text(json.dumps(facts, indent=2, ensure_ascii=False))


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
    return fact


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
    raise FileNotFoundError(f"Memory fact '{fact_id}' not found")


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
    raise FileNotFoundError(f"Memory fact '{fact_id}' not found")


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


def recall(query: str, limit: int = 5) -> list[MemoryFact]:
    """Semantic recall — find facts matching a query.

    Simple text search for now. Will be replaced with vector search when Pinecone is connected.
    """
    facts = get_facts(active_only=True, limit=200)
    query_lower = query.lower()

    scored = []
    for fact in facts:
        score = 0.0
        content_lower = fact.content.lower()

        # Exact match
        if query_lower in content_lower:
            score += 1.0

        # Word overlap
        query_words = set(query_lower.split())
        content_words = set(content_lower.split())
        overlap = query_words & content_words
        if overlap:
            score += len(overlap) / max(len(query_words), 1)

        # Tag match
        for tag in fact.tags:
            if tag.lower() in query_lower:
                score += 0.3

        # Confidence boost
        score *= (0.5 + fact.confidence * 0.5)

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
