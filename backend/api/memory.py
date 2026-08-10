"""Memory API routes — 4-layer agent memory."""
from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel
from typing import Any
from ..services.memory import MemoryLayer
from ..services import memory as svc
from ..core.auth import get_token_dep

router = APIRouter(prefix="/api/memory", tags=["memory"])
auth = get_token_dep()


class AddFactRequest(BaseModel):
    content: str
    layer: str = "inbox"
    source: str = ""
    confidence: float = 0.5
    ttl_hours: int | None = None
    tags: list[str] = []
    related_docs: list[str] = []


@router.post("/facts")
def add_fact(req: AddFactRequest, _=Depends(auth)):
    layer = MemoryLayer(req.layer)
    fact = svc.add_fact(
        content=req.content,
        layer=layer,
        source=req.source,
        confidence=req.confidence,
        ttl_hours=req.ttl_hours,
        tags=req.tags,
        related_docs=req.related_docs,
    )
    return fact.model_dump()


@router.get("/facts")
def list_facts(
    layer: str | None = None,
    tags: str | None = None,
    min_confidence: float = 0.0,
    limit: int = 50,
    _=Depends(auth),
):
    layer_enum = MemoryLayer(layer) if layer else None
    tag_list = tags.split(",") if tags else None
    facts = svc.get_facts(layer=layer_enum, tags=tag_list, min_confidence=min_confidence, limit=limit)
    return [f.model_dump() for f in facts]


@router.get("/facts/{fact_id}")
def get_fact(fact_id: str, _=Depends(auth)):
    return svc.get_fact(fact_id).model_dump()


class UpdateFactRequest(BaseModel):
    content: str | None = None
    confidence: float | None = None
    tags: list[str] | None = None


@router.patch("/facts/{fact_id}")
def update_fact(fact_id: str, req: UpdateFactRequest, _=Depends(auth)):
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None}
    return svc.update_fact(fact_id, **kwargs).model_dump()


class SupersedeRequest(BaseModel):
    new_content: str
    source: str = ""
    confidence: float = 0.5


@router.post("/facts/{fact_id}/supersede")
def supersede(fact_id: str, req: SupersedeRequest, _=Depends(auth)):
    return svc.supersede(fact_id, req.new_content, req.source, req.confidence).model_dump()


class PromoteRequest(BaseModel):
    to_layer: str


@router.post("/facts/{fact_id}/promote")
def promote(fact_id: str, req: PromoteRequest, _=Depends(auth)):
    return svc.promote(fact_id, MemoryLayer(req.to_layer)).model_dump()


@router.get("/recall")
def recall(q: str = Query(...), limit: int = 5, _=Depends(auth)):
    facts = svc.recall(q, limit=limit)
    return [f.model_dump() for f in facts]


@router.get("/stats")
def stats(_=Depends(auth)):
    return svc.get_stats()


class IngestRequest(BaseModel):
    doc_id: str
    content: str
    source: str = ""


@router.post("/ingest")
def ingest(req: IngestRequest, _=Depends(auth)):
    facts = svc.ingest_from_document(req.doc_id, req.content, req.source)
    return {"ingested": len(facts), "facts": [f.model_dump() for f in facts]}


@router.post("/cleanup")
def cleanup(_=Depends(auth)):
    removed = svc.cleanup_expired()
    return {"removed": removed}
