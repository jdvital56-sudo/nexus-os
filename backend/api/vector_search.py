"""Vector search API routes."""
from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel
from ..services import vector_store as svc
from ..core.auth import get_token_dep

router = APIRouter(prefix="/api/vectors", tags=["vectors"])
auth = get_token_dep()


@router.get("/stats")
def stats(_=Depends(auth)):
    return svc.get_stats()


@router.get("/search")
def search(q: str = Query(...), limit: int = 5, min_score: float = 0.0, _=Depends(auth)):
    results = svc.search_vectors(q, limit=limit, min_score=min_score)
    return {"query": q, "count": len(results), "results": results}


class AddVectorRequest(BaseModel):
    id: str
    text: str
    metadata: dict = {}


@router.post("")
def add_vector(req: AddVectorRequest, _=Depends(auth)):
    ok = svc.add_vector(req.id, req.text, req.metadata)
    return {"ok": ok}


@router.delete("/{vector_id}")
def remove_vector(vector_id: str, _=Depends(auth)):
    ok = svc.remove_vector(vector_id)
    return {"ok": ok}


@router.post("/sync/memory")
def sync_memory(_=Depends(auth)):
    synced = svc.sync_from_memory()
    return {"synced": synced}


@router.post("/sync/documents")
def sync_documents(_=Depends(auth)):
    synced = svc.sync_from_documents()
    return {"synced": synced}
