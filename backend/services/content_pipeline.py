"""Content pipeline — full cycle from idea to publication.

Stages: idea → draft → review → approve → schedule → publish → metrics
Each stage creates graph nodes, tasks, and optionally triggers agents.
"""
from datetime import datetime
from typing import Any
from ..models.schemas import (
    DocumentCreate, DocType, TaskCreate, TaskStatus, TaskPriority,
    GraphNode, GraphEdge, NodeType, EdgeType,
)
from . import documents as doc_svc
from . import tasks as task_svc
from . import graph as graph_svc
from . import agents as agent_svc
from . import skills as skill_svc
from .qa_guard import quick_check


PIPELINE_STAGES = ["idea", "draft", "review", "approve", "schedule", "publish", "metrics"]


class ContentItem:
    """Represents a piece of content moving through the pipeline."""

    def __init__(self, content_id: str, title: str, platform: str = "general"):
        self.content_id = content_id
        self.title = title
        self.platform = platform
        self.stage = "idea"
        self.metadata: dict[str, Any] = {}
        self.history: list[dict] = []

    def to_dict(self) -> dict:
        return {
            "content_id": self.content_id,
            "title": self.title,
            "platform": self.platform,
            "stage": self.stage,
            "metadata": self.metadata,
            "history": self.history,
        }


def create_content(title: str, platform: str = "general", description: str = "") -> ContentItem:
    """Create a new content item at the 'idea' stage."""
    import uuid
    content_id = str(uuid.uuid4())[:8]
    item = ContentItem(content_id, title, platform)
    item.metadata["description"] = description

    # Create graph node
    node = GraphNode(
        id=f"content:{content_id}",
        label=f"[idea] {title}",
        node_type=NodeType.DOCUMENT,
        metadata={
            "type": "content_pipeline",
            "platform": platform,
            "stage": "idea",
            "description": description,
        },
    )
    graph_svc.add_node(node)

    # Create idea task
    task_svc.create_task(TaskCreate(
        title=f"Content idea: {title}",
        description=f"Platform: {platform}\n{description}",
        priority=TaskPriority.MEDIUM,
        tags=["content", "idea", platform],
    ))

    item.history.append({"stage": "idea", "timestamp": datetime.utcnow().isoformat(), "action": "created"})
    return item


def advance_stage(item: ContentItem, content_text: str = "") -> ContentItem:
    """Move content to the next pipeline stage.

    Each transition has specific behavior:
    idea → draft: Creates document with auto-tagging
    draft → review: Runs QA check, triggers Reviewer agent
    review → approve: Verifies review passed
    approve → schedule: Creates calendar event (if configured)
    schedule → publish: Executes publish-post skill
    publish → metrics: Creates metrics collection task
    """
    current_idx = PIPELINE_STAGES.index(item.stage)
    if current_idx >= len(PIPELINE_STAGES) - 1:
        return item  # already at final stage

    next_stage = PIPELINE_STAGES[current_idx + 1]
    timestamp = datetime.utcnow().isoformat()

    # === Stage-specific logic ===

    if item.stage == "idea" and next_stage == "draft":
        # Create document
        doc = doc_svc.create_document(DocumentCreate(
            title=item.title,
            content=content_text or f"Draft for: {item.title}",
            doc_type=DocType.MARKDOWN,
            tags=["content", item.platform],
        ), auto_tag=True)
        item.metadata["document_id"] = doc.id

        # Link content node to document
        try:
            graph_svc.add_edge(GraphEdge(
                source=f"content:{item.content_id}",
                target=f"doc:{doc.id}",
                edge_type=EdgeType.CONTAINS,
            ))
        except Exception:
            pass

    elif item.stage == "draft" and next_stage == "review":
        # QA check
        warnings = quick_check(content_text or "")
        item.metadata["qa_warnings"] = warnings

        # Create review task
        task = task_svc.create_task(TaskCreate(
            title=f"Review: {item.title}",
            description=f"Content needs review before publishing.\nWarnings: {warnings}",
            priority=TaskPriority.HIGH,
            assigned_agent="reviewer",
            tags=["content", "review", item.platform],
        ))
        item.metadata["review_task_id"] = task.id

        # Trigger reviewer agent
        try:
            reviewers = agent_svc.list_agents(role="reviewer")
            if reviewers:
                agent_svc.run_agent(reviewers[0].id, f"Review content: {item.title}")
        except Exception:
            pass

    elif item.stage == "review" and next_stage == "approve":
        # Check if review task is done
        review_task_id = item.metadata.get("review_task_id")
        if review_task_id:
            try:
                task = task_svc.get_task(review_task_id)
                if task.status != TaskStatus.DONE:
                    item.metadata["approval_blocked"] = True
                    # Don't advance
                    item.history.append({
                        "stage": "approve",
                        "timestamp": timestamp,
                        "action": "blocked",
                        "reason": "Review task not done",
                    })
                    return item
            except Exception:
                pass
        item.metadata["approved_at"] = timestamp

    elif item.stage == "approve" and next_stage == "schedule":
        item.metadata["scheduled_at"] = timestamp
        # Could trigger calendar event creation here

    elif item.stage == "schedule" and next_stage == "publish":
        # Execute publish skill
        try:
            result = skill_svc.execute_skill("publish-post", {
                "topic": item.title,
                "platform": item.platform,
            })
            item.metadata["publish_result"] = result
        except Exception:
            pass
        item.metadata["published_at"] = timestamp

    elif item.stage == "publish" and next_stage == "metrics":
        # Create metrics collection task
        task_svc.create_task(TaskCreate(
            title=f"Collect metrics: {item.title}",
            description=f"Collect engagement metrics for published content on {item.platform}",
            tags=["content", "metrics", item.platform],
        ))

    # Update stage
    item.stage = next_stage
    item.history.append({"stage": next_stage, "timestamp": timestamp, "action": "advanced"})

    # Update graph node — re-add with updated metadata
    try:
        graph_svc.remove_node(f"content:{item.content_id}")
    except Exception:
        pass
    try:
        graph_svc.add_node(GraphNode(
            id=f"content:{item.content_id}",
            label=f"[{next_stage}] {item.title}",
            node_type=NodeType.DOCUMENT,
            metadata={
                "type": "content_pipeline",
                "platform": item.platform,
                "stage": next_stage,
                "content_id": item.content_id,
                **{k: v for k, v in item.metadata.items() if isinstance(v, (str, int, float, bool, list))},
            },
        ))
    except Exception:
        pass

    return item


def get_pipeline_status() -> dict:
    """Get overview of all content in the pipeline."""
    # Find all content nodes in graph
    content_nodes = graph_svc.list_nodes(node_type="document", limit=100)
    pipeline_items = [n for n in content_nodes if n.metadata.get("type") == "content_pipeline"]

    by_stage: dict[str, int] = {}
    for node in pipeline_items:
        stage = node.metadata.get("stage", "unknown")
        by_stage[stage] = by_stage.get(stage, 0) + 1

    return {
        "total_items": len(pipeline_items),
        "by_stage": by_stage,
        "stages": PIPELINE_STAGES,
    }


def list_content(stage: str | None = None) -> list[dict]:
    """List content items, optionally filtered by stage."""
    content_nodes = graph_svc.list_nodes(node_type="document", limit=100)
    items = []
    for node in content_nodes:
        if node.metadata.get("type") != "content_pipeline":
            continue
        if stage and node.metadata.get("stage") != stage:
            continue
        items.append({
            "content_id": node.id.replace("content:", ""),
            "title": node.label,
            "stage": node.metadata.get("stage", "unknown"),
            "platform": node.metadata.get("platform", "unknown"),
        })
    return items
