"""Knowledge graph API routes."""
from fastapi import APIRouter, Query, Depends
from ..models.schemas import GraphNode, GraphEdge, GraphStats
from ..services import graph as svc
from ..core.auth import get_token_dep

router = APIRouter(prefix="/api/graph", tags=["graph"])
auth = get_token_dep()


@router.get("/stats", response_model=GraphStats)
def stats(_=Depends(auth)):
    return svc.get_stats()


@router.get("/nodes", response_model=list[GraphNode])
def list_nodes(node_type: str | None = None, label_contains: str | None = None, limit: int = 50, _=Depends(auth)):
    return svc.list_nodes(node_type=node_type, label_contains=label_contains, limit=limit)


@router.get("/nodes/{node_id}", response_model=GraphNode)
def get_node(node_id: str, _=Depends(auth)):
    return svc.get_node(node_id)


@router.post("/nodes", response_model=GraphNode, status_code=201)
def add_node(node: GraphNode, _=Depends(auth)):
    return svc.add_node(node)


@router.delete("/nodes/{node_id}")
def remove_node(node_id: str, _=Depends(auth)):
    svc.remove_node(node_id)
    return {"ok": True}


@router.post("/edges", response_model=GraphEdge, status_code=201)
def add_edge(edge: GraphEdge, _=Depends(auth)):
    return svc.add_edge(edge)


@router.delete("/edges/{source}/{target}")
def remove_edge(source: str, target: str, _=Depends(auth)):
    svc.remove_edge(source, target)
    return {"ok": True}


@router.get("/neighbors/{node_id}")
def neighbors(node_id: str, depth: int = 1, _=Depends(auth)):
    return svc.get_neighbors(node_id, depth=depth)


@router.get("/search", response_model=list[GraphNode])
def search(q: str = Query(...), limit: int = 20, _=Depends(auth)):
    return svc.search(q, limit=limit)
