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


# === Builder ===

def orient_builder(ctx: AgentContext) -> dict:
    """Builder: Check tasks, identify what needs to be built."""
    tasks = task_svc.list_tasks(status="todo")
    in_progress = task_svc.list_tasks(status="in_progress")
    ctx.log_msg(f"Orient: {len(tasks)} todo tasks, {len(in_progress)} in progress")
    return {"todo": len(tasks), "in_progress": len(in_progress), "tasks": [t.model_dump() for t in tasks[:5]]}


def observe_builder(ctx: AgentContext, orient_data: dict) -> list:
    """Builder: Collect buildable tasks."""
    buildable = []
    for t in orient_data.get("tasks", []):
        if "build" in t["title"].lower() or "create" in t["title"].lower() or "implement" in t["title"].lower():
            buildable.append(t)
    ctx.log_msg(f"Observe: {len(buildable)} buildable tasks found")
    return buildable


def think_builder(ctx: AgentContext, tasks: list) -> list[dict]:
    """Builder: Plan build steps."""
    actions = []
    for t in tasks:
        actions.append({
            "action": "build",
            "task_id": t["id"],
            "title": t["title"],
            "plan": f"Implement: {t['title']}",
        })
    ctx.log_msg(f"Think: planned {len(actions)} builds")
    return actions


def act_builder(ctx: AgentContext, actions: list[dict]) -> list[dict]:
    """Builder: Mark tasks as in_progress, create implementation notes."""
    results = []
    for action in actions:
        if action["action"] == "build":
            try:
                task_svc.update_task(action["task_id"], task_svc.TaskUpdate(status=task_svc.TaskStatus.IN_PROGRESS))
                graph_svc.add_node(GraphNode(
                    id=f"build:{action['task_id']}",
                    label=f"Build: {action['title']}",
                    node_type=NodeType.DECISION,
                    metadata={"task_id": action["task_id"], "status": "in_progress"},
                ))
                results.append({"task_id": action["task_id"], "status": "started"})
                ctx.log_msg(f"Act: started building '{action['title']}'")
            except Exception as e:
                results.append({"task_id": action["task_id"], "status": "error", "error": str(e)})
    return results


def verify_builder(ctx: AgentContext, act_results: list[dict]) -> dict:
    """Builder: Verify builds."""
    started = sum(1 for r in act_results if r["status"] == "started")
    ctx.log_msg(f"Verify: {started} builds started")
    return {"builds_started": started}


# === Researcher ===

def orient_researcher(ctx: AgentContext) -> dict:
    """Researcher: Identify knowledge gaps."""
    stats = graph_svc.get_stats()
    from . import memory as mem_svc
    mem_stats = mem_svc.get_stats()
    active = mem_stats.get('active', 0)
    ctx.log_msg(f"Orient: graph has {stats.nodes} nodes, memory has {active} active facts")
    return {"graph": stats.model_dump(), "memory": mem_stats}


def observe_researcher(ctx: AgentContext, orient_data: dict) -> list:
    """Researcher: Find sparse areas in the graph."""
    nodes = graph_svc.list_nodes(limit=100)
    sparse = []
    for node in nodes:
        try:
            neighbors = graph_svc.get_neighbors(node.id, depth=1)
            if len(neighbors["edges"]) < 2:
                sparse.append({"id": node.id, "label": node.label, "connections": len(neighbors["edges"])})
        except Exception:
            pass
    ctx.log_msg(f"Observe: {len(sparse)} sparse nodes found")
    return sparse[:10]


def think_researcher(ctx: AgentContext, sparse: list) -> list[dict]:
    """Researcher: Plan research tasks."""
    actions = []
    for node in sparse:
        actions.append({
            "action": "research",
            "node_id": node["id"],
            "label": node["label"],
            "connections": node["connections"],
        })
    ctx.log_msg(f"Think: {len(actions)} research tasks planned")
    return actions


def act_researcher(ctx: AgentContext, actions: list[dict]) -> list[dict]:
    """Researcher: Create research tasks and notes."""
    results = []
    for action in actions:
        if action["action"] == "research":
            try:
                task = task_svc.create_task(task_svc.TaskCreate(
                    title=f"Research: {action['label']}",
                    description=f"Node '{action['node_id']}' has only {action['connections']} connections. Find related information.",
                    assigned_agent="librarian",
                    tags=["research", "auto"],
                ))
                results.append({"node_id": action["node_id"], "status": "task_created", "task_id": task.id})
                ctx.log_msg(f"Act: created research task for '{action['label']}'")
            except Exception as e:
                results.append({"node_id": action["node_id"], "status": "error", "error": str(e)})
    return results


def verify_researcher(ctx: AgentContext, act_results: list[dict]) -> dict:
    """Researcher: Summarize research plan."""
    tasks_created = sum(1 for r in act_results if r.get("status") == "task_created")
    ctx.log_msg(f"Verify: {tasks_created} research tasks created")
    return {"research_tasks": tasks_created}


# === Monitor ===

def orient_monitor(ctx: AgentContext) -> dict:
    """Monitor: Check system health."""
    stats = graph_svc.get_stats()
    tasks = task_svc.list_tasks()
    blocked = [t for t in tasks if t.status.value == "blocked"]
    overdue = [t for t in tasks if t.status.value == "in_progress"]  # simplified
    ctx.log_msg(f"Orient: {stats.nodes} nodes, {len(tasks)} tasks, {len(blocked)} blocked")
    return {"graph": stats.model_dump(), "total_tasks": len(tasks), "blocked": len(blocked), "in_progress": len(overdue)}


def observe_monitor(ctx: AgentContext, orient_data: dict) -> list:
    """Monitor: Detect anomalies."""
    issues = []
    if orient_data["blocked"] > 3:
        issues.append({"type": "too_many_blocked", "count": orient_data["blocked"], "severity": "warning"})
    if orient_data["in_progress"] > 10:
        issues.append({"type": "too_many_in_progress", "count": orient_data["in_progress"], "severity": "warning"})
    if orient_data["graph"]["nodes"] == 0:
        issues.append({"type": "empty_graph", "severity": "info"})
    ctx.log_msg(f"Observe: {len(issues)} issues detected")
    return issues


def think_monitor(ctx: AgentContext, issues: list) -> list[dict]:
    """Monitor: Decide actions for issues."""
    actions = []
    for issue in issues:
        if issue["type"] == "too_many_blocked":
            actions.append({"action": "alert", "message": f"{issue['count']} tasks are blocked. Review and unblock.", "severity": issue["severity"]})
        elif issue["type"] == "empty_graph":
            actions.append({"action": "alert", "message": "Knowledge graph is empty. Import data.", "severity": "info"})
    ctx.log_msg(f"Think: {len(actions)} actions planned")
    return actions


def act_monitor(ctx: AgentContext, actions: list[dict]) -> list[dict]:
    """Monitor: Create alert tasks."""
    results = []
    for action in actions:
        if action["action"] == "alert":
            try:
                task = task_svc.create_task(task_svc.TaskCreate(
                    title=f"[MONITOR] {action['message'][:50]}",
                    description=action["message"],
                    priority=task_svc.TaskPriority.HIGH if action["severity"] == "warning" else task_svc.TaskPriority.MEDIUM,
                    tags=["monitor", "alert", "auto"],
                ))
                results.append({"status": "alert_created", "task_id": task.id})
                ctx.log_msg(f"Act: alert created — {action['message'][:40]}")
            except Exception as e:
                results.append({"status": "error", "error": str(e)})
    return results


def verify_monitor(ctx: AgentContext, act_results: list[dict]) -> dict:
    """Monitor: Report health status."""
    alerts = sum(1 for r in act_results if r.get("status") == "alert_created")
    ctx.log_msg(f"Verify: {alerts} alerts created, system check complete")
    return {"alerts_created": alerts, "status": "healthy" if alerts == 0 else "attention_needed"}


# === Jarvis (orchestrator) ===

def orient_jarvis(ctx: AgentContext) -> dict:
    """Jarvis: Read full system state."""
    stats = graph_svc.get_stats()
    tasks = task_svc.list_tasks()
    from . import memory as mem_svc
    mem_stats = mem_svc.get_stats()
    agents = ["librarian", "reviewer", "builder", "researcher", "monitor"]
    active = mem_stats.get('active', 0)
    ctx.log_msg(f"Orient: {stats.nodes} nodes, {len(tasks)} tasks, {active} memories")
    return {"graph": stats.model_dump(), "tasks": len(tasks), "memory": mem_stats, "agents": agents}


def observe_jarvis(ctx: AgentContext, orient_data: dict) -> list:
    """Jarvis: Identify what needs attention across all agents."""
    tasks = task_svc.list_tasks(status="todo")
    critical = [t for t in tasks if t.priority.value in ("high", "critical")]
    ctx.log_msg(f"Observe: {len(critical)} high-priority tasks")
    return [t.model_dump() for t in critical[:5]]


def think_jarvis(ctx: AgentContext, critical_tasks: list) -> list[dict]:
    """Jarvis: Decide which agent handles each task."""
    actions = []
    for t in critical_tasks:
        # Route based on tags
        assigned = "librarian"  # default
        if "review" in t.get("tags", []):
            assigned = "reviewer"
        elif "build" in t.get("tags", []) or "implement" in t.get("tags", []):
            assigned = "builder"
        elif "research" in t.get("tags", []):
            assigned = "researcher"
        actions.append({
            "action": "delegate",
            "task_id": t["id"],
            "title": t["title"],
            "assign_to": assigned,
        })
    ctx.log_msg(f"Think: {len(actions)} tasks delegated")
    return actions


def act_jarvis(ctx: AgentContext, actions: list[dict]) -> list[dict]:
    """Jarvis: Delegate tasks to other agents."""
    results = []
    for action in actions:
        if action["action"] == "delegate":
            try:
                task_svc.update_task(action["task_id"], task_svc.TaskUpdate(assigned_agent=action["assign_to"]))
                results.append({"task_id": action["task_id"], "delegated_to": action["assign_to"], "status": "delegated"})
                ctx.log_msg(f"Act: delegated '{action['title'][:30]}' to {action['assign_to']}")
            except Exception as e:
                results.append({"task_id": action["task_id"], "status": "error", "error": str(e)})
    return results


def verify_jarvis(ctx: AgentContext, act_results: list[dict]) -> dict:
    """Jarvis: Summarize orchestration."""
    delegated = sum(1 for r in act_results if r.get("status") == "delegated")
    ctx.log_msg(f"Verify: {delegated} tasks delegated to agents")
    return {"delegated": delegated, "status": "orchestrated"}


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
    AgentRole.BUILDER: {
        "orient": orient_builder,
        "observe": observe_builder,
        "think": think_builder,
        "act": act_builder,
        "verify": verify_builder,
    },
    AgentRole.RESEARCHER: {
        "orient": orient_researcher,
        "observe": observe_researcher,
        "think": think_researcher,
        "act": act_researcher,
        "verify": verify_researcher,
    },
    AgentRole.MONITOR: {
        "orient": orient_monitor,
        "observe": observe_monitor,
        "think": think_monitor,
        "act": act_monitor,
        "verify": verify_monitor,
    },
    AgentRole.JARVIS: {
        "orient": orient_jarvis,
        "observe": observe_jarvis,
        "think": think_jarvis,
        "act": act_jarvis,
        "verify": verify_jarvis,
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
