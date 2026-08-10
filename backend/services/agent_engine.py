"""Agent execution engine — Orient-Observe-Think-Act-Verify cycle.

This is the real execution loop for NEXSYS agents.
Each agent role implements the 5 phases differently.
"""
import json
import time
from datetime import datetime
from ..models.schemas import Agent, AgentRole, AgentStatus, GraphNode, NodeType
from . import graph as graph_svc
from . import documents as doc_svc
from . import tasks as task_svc


class AgentContext:
    """Shared context for an agent run."""
    def __init__(self, agent: Agent, task: str, extra: dict | None = None):
        self.agent = agent
        self.task = task
        self.extra = extra or {}
        self.log: list[str] = []
        self.result: dict = {}
        self.start_time = time.time()

    def log_msg(self, msg: str):
        ts = f"[{time.time() - self.start_time:.1f}s]"
        self.log.append(f"{ts} {msg}")

    @property
    def duration_ms(self) -> int:
        return int((time.time() - self.start_time) * 1000)


# === Phase implementations per role ===

def orient_librarian(ctx: AgentContext) -> dict:
    """Librarian: Read graph state, identify gaps."""
    stats = graph_svc.get_stats()
    docs = doc_svc.list_documents()
    ctx.log_msg(f"Orient: graph has {stats.nodes} nodes, {stats.edges} edges")
    ctx.log_msg(f"Orient: {len(docs)} documents in system")
    # Find unlinked documents (no graph node)
    linked_ids = set()
    for n in graph_svc.list_nodes(node_type="document", limit=500):
        doc_id = n.metadata.get("doc_id")
        if doc_id:
            linked_ids.add(doc_id)
    unlinked = [d for d in docs if d.id not in linked_ids]
    ctx.log_msg(f"Orient: {len(unlinked)} documents not linked to graph")
    return {"stats": stats.model_dump(), "unlinked_count": len(unlinked), "unlinked": [d.id for d in unlinked]}


def observe_librarian(ctx: AgentContext, orient_data: dict) -> list:
    """Librarian: Collect documents that need processing."""
    unlinked_ids = orient_data.get("unlinked", [])
    docs_to_process = []
    for doc_id in unlinked_ids:
        try:
            doc = doc_svc.get_document(doc_id)
            docs_to_process.append(doc)
        except Exception:
            pass
    ctx.log_msg(f"Observe: collected {len(docs_to_process)} documents for processing")
    return docs_to_process


def think_librarian(ctx: AgentContext, docs: list) -> list[dict]:
    """Librarian: Decide what actions to take for each document."""
    actions = []
    for doc in docs:
        actions.append({
            "action": "link_document",
            "doc_id": doc.id,
            "title": doc.title,
            "tags": doc.tags,
            "reason": f"Document '{doc.title}' has {len(doc.tags)} tags, not linked to graph",
        })
    ctx.log_msg(f"Think: planned {len(actions)} actions")
    return actions


def act_librarian(ctx: AgentContext, actions: list[dict]) -> list[dict]:
    """Librarian: Execute actions — create graph nodes and edges."""
    results = []
    from .tagger import create_document_graph_nodes, create_concept_node
    for action in actions:
        if action["action"] == "link_document":
            try:
                doc_node, tag_edges = create_document_graph_nodes(
                    action["doc_id"], action["title"], action["tags"]
                )
                graph_svc.add_node(doc_node)
                for tag in action["tags"]:
                    try:
                        graph_svc.add_node(create_concept_node(tag))
                    except Exception:
                        pass
                edges_added = 0
                for edge in tag_edges:
                    try:
                        graph_svc.add_edge(edge)
                        edges_added += 1
                    except Exception:
                        pass
                results.append({"doc_id": action["doc_id"], "status": "linked", "edges": edges_added})
                ctx.log_msg(f"Act: linked document '{action['title']}' with {edges_added} edges")
            except Exception as e:
                results.append({"doc_id": action["doc_id"], "status": "error", "error": str(e)})
                ctx.log_msg(f"Act: FAILED to link '{action['title']}': {e}")
    return results


def verify_librarian(ctx: AgentContext, act_results: list[dict]) -> dict:
    """Librarian: Verify graph consistency after changes."""
    stats = graph_svc.get_stats()
    linked = sum(1 for r in act_results if r["status"] == "linked")
    errors = sum(1 for r in act_results if r["status"] == "error")
    ctx.log_msg(f"Verify: {linked} linked, {errors} errors, graph now has {stats.nodes} nodes, {stats.edges} edges")
    return {
        "linked": linked,
        "errors": errors,
        "graph_nodes": stats.nodes,
        "graph_edges": stats.edges,
    }


# === Reviewer (QA Guard) ===

def orient_reviewer(ctx: AgentContext) -> dict:
    """Reviewer: Read recent changes to the graph."""
    stats = graph_svc.get_stats()
    recent_nodes = graph_svc.list_nodes(limit=20)
    ctx.log_msg(f"Orient: graph has {stats.nodes} nodes, reviewing {len(recent_nodes)} recent")
    return {"stats": stats.model_dump(), "recent_count": len(recent_nodes)}


def observe_reviewer(ctx: AgentContext, orient_data: dict) -> list:
    """Reviewer: Collect nodes/edges to check."""
    nodes = graph_svc.list_nodes(limit=50)
    issues = []
    # Check for orphan nodes (no edges)
    for node in nodes:
        try:
            neighbors = graph_svc.get_neighbors(node.id, depth=1)
            if len(neighbors["edges"]) == 0 and node.node_type.value not in ("concept",):
                issues.append({
                    "type": "orphan_node",
                    "node_id": node.id,
                    "label": node.label,
                    "severity": "warning",
                })
        except Exception:
            pass
    ctx.log_msg(f"Observe: found {len(issues)} potential issues")
    return issues


def think_reviewer(ctx: AgentContext, issues: list) -> list[dict]:
    """Reviewer: Decide which issues need fixing."""
    actions = []
    for issue in issues:
        if issue["type"] == "orphan_node":
            actions.append({
                "action": "flag_orphan",
                "node_id": issue["node_id"],
                "label": issue["label"],
                "recommendation": "Consider linking to related documents or concepts",
            })
    ctx.log_msg(f"Think: {len(actions)} issues need attention")
    return actions


def act_reviewer(ctx: AgentContext, actions: list[dict]) -> list[dict]:
    """Reviewer: Create review tasks for flagged issues."""
    results = []
    for action in actions:
        if action["action"] == "flag_orphan":
            try:
                task = task_svc.create_task(task_svc.TaskCreate(
                    title=f"Link orphan node: {action['label']}",
                    description=f"Node '{action['node_id']}' has no connections. {action['recommendation']}",
                    assigned_agent="librarian",
                    tags=["review", "auto"],
                ))
                results.append({"action": "flag_orphan", "status": "task_created", "task_id": task.id})
                ctx.log_msg(f"Act: created task for orphan '{action['label']}'")
            except Exception as e:
                results.append({"action": "flag_orphan", "status": "error", "error": str(e)})
    return results


def verify_reviewer(ctx: AgentContext, act_results: list[dict]) -> dict:
    """Reviewer: Summarize review findings."""
    tasks_created = sum(1 for r in act_results if r.get("status") == "task_created")
    ctx.log_msg(f"Verify: {tasks_created} tasks created for issues")
    return {"tasks_created": tasks_created, "total_issues": len(act_results)}


# === Generic stub for other roles ===

def generic_cycle(ctx: AgentContext) -> dict:
    """Generic cycle stub for roles not yet implemented."""
    ctx.log_msg(f"Orient: role '{ctx.agent.role.value}' — generic cycle")
    ctx.log_msg(f"Observe: task = '{ctx.task}'")
    ctx.log_msg(f"Think: this role is not yet fully implemented")
    ctx.log_msg(f"Act: logging task as pending")
    ctx.log_msg(f"Verify: no changes made")
    return {"status": "stub", "message": f"Role '{ctx.agent.role.value}' not yet fully implemented"}


# === Main executor ===

ROLE_CYCLES = {
    AgentRole.LIBRARIAN: {
        "orient": orient_librarian,
        "observe": observe_librarian,
        "think": think_librarian,
        "act": act_librarian,
        "verify": verify_librarian,
    },
    AgentRole.REVIEWER: {
        "orient": orient_reviewer,
        "observe": observe_reviewer,
        "think": think_reviewer,
        "act": act_reviewer,
        "verify": verify_reviewer,
    },
}


def execute_cycle(agent: Agent, task: str, context: dict | None = None) -> dict:
    """Execute the full Orient-Observe-Think-Act-Verify cycle for an agent."""
    ctx = AgentContext(agent, task, context)

    cycle = ROLE_CYCLES.get(agent.role)
    if not cycle:
        result = generic_cycle(ctx)
        return {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "role": agent.role.value,
            "status": "completed",
            "output": "\n".join(ctx.log),
            "result": result,
            "duration_ms": ctx.duration_ms,
        }

    try:
        ctx.log_msg(f"=== Starting {agent.role.value} cycle ===")

        # Orient
        orient_data = cycle["orient"](ctx)

        # Observe
        observed = cycle["observe"](ctx, orient_data)

        # Think
        actions = cycle["think"](ctx, observed)

        # Act
        act_results = cycle["act"](ctx, actions)

        # Verify
        verify_result = cycle["verify"](ctx, act_results)

        ctx.log_msg(f"=== Cycle complete ===")

        return {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "role": agent.role.value,
            "status": "completed",
            "output": "\n".join(ctx.log),
            "result": {
                "orient": orient_data,
                "observed_count": len(observed) if isinstance(observed, list) else 0,
                "actions_planned": len(actions) if isinstance(actions, list) else 0,
                "act_results": act_results if isinstance(act_results, list) else [],
                "verify": verify_result,
            },
            "duration_ms": ctx.duration_ms,
        }
    except Exception as e:
        ctx.log_msg(f"ERROR: {e}")
        return {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "role": agent.role.value,
            "status": "error",
            "output": "\n".join(ctx.log),
            "error": str(e),
            "duration_ms": ctx.duration_ms,
        }
