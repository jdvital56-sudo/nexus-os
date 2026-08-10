"""Webhook endpoint — accepts incoming data from external sources.

Supports: generic text, call transcripts, voice messages, CRM events.
Each webhook auto-tags, links to graph, and optionally triggers an agent.
"""
from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel
from typing import Any
from ..models.schemas import DocumentCreate, DocType, NodeType, GraphNode
from ..services import documents as doc_svc
from ..services import graph as graph_svc
from ..services import agents as agent_svc
from ..core.auth import get_token_dep

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
auth = get_token_dep()


class WebhookPayload(BaseModel):
    source: str  # "call", "voice", "crm", "email", "custom"
    title: str
    content: str
    metadata: dict[str, Any] = {}
    auto_process: bool = True  # auto-tag + link + optionally trigger agent
    trigger_agent: str | None = None  # agent role to trigger after ingestion


class WebhookResponse(BaseModel):
    document_id: str
    tags: list[str]
    graph_linked: bool
    agent_triggered: str | None = None
    warnings: list[str] = []


@router.post("", response_model=WebhookResponse)
def ingest_webhook(payload: WebhookPayload, _=Depends(auth)):
    """Ingest data from external source into NEXSYS.

    Flow:
    1. Create document with auto-tagging
    2. Link to knowledge graph
    3. Optionally trigger an agent for processing
    """
    from ..services.qa_guard import quick_check

    # Quick safety check
    warnings = quick_check(payload.content)

    # Map source to doc_type
    doc_type_map = {
        "call": DocType.TEXT,
        "voice": DocType.TEXT,
        "crm": DocType.JSON,
        "email": DocType.TEXT,
        "markdown": DocType.MARKDOWN,
    }
    doc_type = doc_type_map.get(payload.source, DocType.TEXT)

    # Create document with auto-tagging
    doc = doc_svc.create_document(DocumentCreate(
        title=payload.title,
        content=payload.content,
        doc_type=doc_type,
        tags=[],
        source=f"webhook:{payload.source}",
    ), auto_tag=True)

    # Add source metadata as graph node
    source_node = GraphNode(
        id=f"source:{payload.source}:{doc.id}",
        label=f"{payload.source}: {payload.title}",
        node_type=NodeType.SESSION,
        metadata={**payload.metadata, "doc_id": doc.id, "source_type": payload.source},
    )
    try:
        graph_svc.add_node(source_node)
        # Link source to document
        from ..models.schemas import GraphEdge, EdgeType
        graph_svc.add_edge(GraphEdge(
            source=source_node.id,
            target=f"doc:{doc.id}",
            edge_type=EdgeType.CREATED_BY,
        ))
    except Exception:
        pass

    # Optionally trigger agent
    agent_triggered = None
    if payload.trigger_agent and payload.auto_process:
        try:
            agents = agent_svc.list_agents(role=payload.trigger_agent)
            if agents:
                result = agent_svc.run_agent(agents[0].id, f"Process webhook: {payload.title}")
                agent_triggered = payload.trigger_agent
        except Exception:
            pass

    return WebhookResponse(
        document_id=doc.id,
        tags=doc.tags,
        graph_linked=True,
        agent_triggered=agent_triggered,
        warnings=warnings,
    )


@router.post("/batch")
def ingest_batch(payloads: list[WebhookPayload], _=Depends(auth)):
    """Batch ingest multiple items."""
    results = []
    for p in payloads:
        results.append(ingest_webhook(p, _))
    return {"count": len(results), "results": results}
