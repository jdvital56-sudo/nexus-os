"""Vector store for semantic search.

Uses sentence-transformers for embeddings and numpy for similarity search.
Falls back to simple text search if sentence-transformers not installed.
"""
import json
import hashlib
import numpy as np
from pathlib import Path
from typing import Any
from ..core.config import DATA_DIR, ensure_data_dir

VECTORS_FILE = DATA_DIR / "vectors.json"
_model = None


def _get_model():
    """Lazy-load sentence-transformers model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
        except ImportError:
            return None
    return _model


def _load_vectors() -> dict:
    ensure_data_dir()
    if VECTORS_FILE.exists():
        return json.loads(VECTORS_FILE.read_text())
    return {"ids": [], "texts": [], "vectors": [], "metadata": []}


def _save_vectors(data: dict):
    ensure_data_dir()
    # Convert numpy arrays to lists for JSON
    save_data = {
        "ids": data["ids"],
        "texts": data["texts"],
        "vectors": [v.tolist() if isinstance(v, np.ndarray) else v for v in data["vectors"]],
        "metadata": data["metadata"],
    }
    VECTORS_FILE.write_text(json.dumps(save_data, indent=2))


def embed_text(text: str) -> list[float] | None:
    """Generate embedding vector for text."""
    model = _get_model()
    if model is None:
        return None
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def add_vector(id: str, text: str, metadata: dict | None = None) -> bool:
    """Add a text with its vector embedding to the store."""
    vector = embed_text(text)
    # Use empty vector if model not available (text search fallback)
    if vector is None:
        vector = []

    data = _load_vectors()

    # Check if ID already exists
    if id in data["ids"]:
        idx = data["ids"].index(id)
        data["texts"][idx] = text
        data["vectors"][idx] = vector
        data["metadata"][idx] = metadata or {}
    else:
        data["ids"].append(id)
        data["texts"].append(text)
        data["vectors"].append(vector)
        data["metadata"].append(metadata or {})

    _save_vectors(data)
    return True


def search_vectors(query: str, limit: int = 5, min_score: float = 0.0) -> list[dict]:
    """Semantic search — find most similar texts to query."""
    data = _load_vectors()
    if not data["vectors"]:
        return []

    # Check if we have real vectors or just empty lists
    has_vectors = any(len(v) > 0 for v in data["vectors"])

    if not has_vectors:
        return _text_search(query, data, limit)

    query_vector = embed_text(query)
    if query_vector is None:
        # Fallback to text search
        return _text_search(query, data, limit)

    # Cosine similarity
    query_arr = np.array(query_vector)
    vectors_arr = np.array(data["vectors"])

    # Normalize
    query_norm = query_arr / (np.linalg.norm(query_arr) + 1e-10)
    vectors_norm = vectors_arr / (np.linalg.norm(vectors_arr, axis=1, keepdims=True) + 1e-10)

    scores = np.dot(vectors_norm, query_norm)

    # Sort by score
    indices = np.argsort(scores)[::-1][:limit]

    results = []
    for idx in indices:
        score = float(scores[idx])
        if score >= min_score:
            results.append({
                "id": data["ids"][idx],
                "text": data["texts"][idx],
                "score": round(score, 4),
                "metadata": data["metadata"][idx],
            })

    return results


def _text_search(query: str, data: dict, limit: int) -> list[dict]:
    """Fallback text search when embeddings unavailable."""
    query_lower = query.lower()
    scored = []
    for i, text in enumerate(data["texts"]):
        text_lower = text.lower()
        # Word overlap
        query_words = set(query_lower.split())
        text_words = set(text_lower.split())
        overlap = query_words & text_words
        if overlap:
            score = len(overlap) / max(len(query_words), 1)
            scored.append((score, i))

    scored.sort(reverse=True)
    results = []
    for score, idx in scored[:limit]:
        results.append({
            "id": data["ids"][idx],
            "text": data["texts"][idx],
            "score": round(score, 4),
            "metadata": data["metadata"][idx],
        })
    return results


def remove_vector(id: str) -> bool:
    """Remove a vector by ID."""
    data = _load_vectors()
    if id not in data["ids"]:
        return False
    idx = data["ids"].index(id)
    data["ids"].pop(idx)
    data["texts"].pop(idx)
    data["vectors"].pop(idx)
    data["metadata"].pop(idx)
    _save_vectors(data)
    return True


def get_stats() -> dict:
    """Vector store statistics."""
    data = _load_vectors()
    model = _get_model()
    return {
        "total_vectors": len(data["ids"]),
        "embedding_model": "all-MiniLM-L6-v2" if model else "none (text search fallback)",
        "embedding_dim": len(data["vectors"][0]) if data["vectors"] else 0,
    }


def sync_from_memory():
    """Sync all memory facts to vector store."""
    from . import memory as mem_svc
    facts = mem_svc.get_facts(active_only=True, limit=500)
    synced = 0
    for fact in facts:
        text = fact.content
        if fact.source:
            text = f"[{fact.source}] {text}"
        if add_vector(f"memory:{fact.id}", text, {"type": "memory", "layer": fact.layer.value, "confidence": fact.confidence}):
            synced += 1
    return synced


def sync_from_documents():
    """Sync all documents to vector store."""
    from . import documents as doc_svc
    docs = doc_svc.list_documents()
    synced = 0
    for doc in docs:
        # Use first 500 chars of content
        text = f"{doc.title}: {doc.content[:500]}"
        if add_vector(f"doc:{doc.id}", text, {"type": "document", "doc_id": doc.id, "tags": doc.tags}):
            synced += 1
    return synced
