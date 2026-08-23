"""Agent execution engine — Orient-Observe-Think-Act-Verify cycle.

This is the real execution loop for NEXSYS agents.
Each agent role implements the 5 phases differently.
"""
import json
import logging
import time
from datetime import datetime
from ..core import eventbus
from ..models.schemas import Agent, AgentRole, AgentStatus, GraphNode, NodeType
from . import budget
from . import graph as graph_svc
from . import documents as doc_svc
from . import tasks as task_svc

logger = logging.getLogger(__name__)


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
    """Reviewer: конкретная задача — уходит в настоящий ревью незакоммиченных
    изменений (git diff + вердикт модели, см. _review_directed). Без задачи —
    прежний обход графа на предмет узлов без единой связи (плановый прогон).

    23.08.2026: раньше эта роль ВСЕГДА заводила ещё одну задачу «кто-то
    пусть свяжет узел» и игнорировала переданную задачу целиком — даже
    попроси её «проверь код» она бы не взглянула ни на один файл. Фаундер
    прямо сказал: агенты должны реально работать, не быть трекерами.
    """
    if ctx.task and ctx.task.strip():
        ctx.log_msg(f"Orient: реальная задача рецензии — «{ctx.task[:80]}»")
        return {"directed": True}
    stats = graph_svc.get_stats()
    recent_nodes = graph_svc.list_nodes(limit=20)
    ctx.log_msg(f"Orient: graph has {stats.nodes} nodes, reviewing {len(recent_nodes)} recent")
    return {"directed": False, "stats": stats.model_dump(), "recent_count": len(recent_nodes)}


def observe_reviewer(ctx: AgentContext, orient_data: dict) -> list:
    """Reviewer: при директиве — сама задача. Иначе — узлы графа без связей,
    как раньше."""
    if orient_data.get("directed"):
        return [{"directed": True, "task": ctx.task}]
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


def think_reviewer(ctx: AgentContext, items: list) -> list[dict]:
    """Reviewer: Decide which issues need fixing — или одна директива ревью."""
    if items and items[0].get("directed"):
        return [{"action": "review_directed", "task": items[0]["task"]}]
    actions = []
    for issue in items:
        if issue["type"] == "orphan_node":
            actions.append({
                "action": "flag_orphan",
                "node_id": issue["node_id"],
                "label": issue["label"],
                "recommendation": "Consider linking to related documents or concepts",
            })
    ctx.log_msg(f"Think: {len(actions)} issues need attention")
    return actions


def _git_diff(ctx: AgentContext) -> str:
    """Diff незакоммиченного в репозитории. Пустая строка — либо ничего не
    менялось, либо git недоступен (не считается ошибкой всего цикла)."""
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    try:
        proc = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception as e:
        ctx.log_msg(f"Act: git diff недоступен — {e}")
        return ""
    diff = proc.stdout.strip()
    # Длинный diff в промпт целиком не влезет разумно — режем, как в
    # content_factory.py режет длинные сценарии
    return diff[:12000] + "\n... (обрезано)" if len(diff) > 12000 else diff


def _review_directed(ctx: AgentContext, task: str) -> dict:
    """Настоящий ревью: задание — это уже сам предмет проверки (qa_guard.py
    кладёт туда содержимое артефакта целиком, голосовая команда — короткую
    просьбу). Если формулировка похожа на просьбу посмотреть код/изменения
    — дополнительно прикладываем git diff незакоммиченного как контекст,
    не заменяем им задание."""
    import asyncio
    import re

    from .llm import LLMService
    from ..core.config import settings

    diff_context = ""
    if re.search(r"код|diff|измен|правк|коммит|code|changes?\b", task, re.IGNORECASE):
        diff = _git_diff(ctx)
        if diff:
            diff_context = f"\n\nDiff незакоммиченных изменений в репозитории:\n{diff}"

    llm = LLMService(provider="deepseek", model="deepseek-chat", api_key=settings.deepseek_api_key)
    prompt = (
        f"{task}{diff_context}\n\n"
        "Дай короткий вердикт по одной из двух форм:\n"
        '— если нашёл реальную проблему: начни строку с "Issue: " и опиши "'
        "конкретно, с местом в тексте/коде, не общими словами;\n"
        '— если всё выглядит нормально: одна строка "OK: " и короткое пояснение.\n'
        "Не выдумывай проблемы ради проблем."
    )
    try:
        verdict = asyncio.run(llm.generate_response(prompt, kind=budget.BACKGROUND)).strip()
    except Exception as e:
        ctx.log_msg(f"Act: вердикт не удался — {e}")
        return {"status": "error", "task": task, "error": str(e)}

    # qa_guard.py разбирает именно ctx.log (result.output), не структурный
    # result — вердикт обязан попасть туда целиком, строка за строкой
    for line in verdict.splitlines():
        if line.strip():
            ctx.log_msg(line.strip())

    from . import memory as mem_svc

    fact = mem_svc.add_fact(
        content=f"Рецензия «{task[:200]}»: {verdict}",
        source="reviewer",
        confidence=0.6,
    )
    ctx.log_msg(f"Act: вердикт записан в память ({fact.id})")
    return {"status": "reviewed", "task": task, "verdict": verdict, "fact_id": fact.id}


def act_reviewer(ctx: AgentContext, actions: list[dict]) -> list[dict]:
    """Reviewer: реальный ревью по директиве, иначе — заводит задачи по
    узлам без связей, как раньше."""
    results = []
    for action in actions:
        if action["action"] == "review_directed":
            results.append(_review_directed(ctx, action["task"]))
        elif action["action"] == "flag_orphan":
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
    """Reviewer: Summarize review findings — или итог настоящего ревью."""
    reviewed = [r for r in act_results if r.get("status") == "reviewed"]
    if reviewed:
        ctx.log_msg(f"Verify: вердикт готов — {reviewed[0]['verdict'][:120]}")
        return {"status": "reviewed", "verdict": reviewed[0]["verdict"], "fact_id": reviewed[0]["fact_id"]}
    tasks_created = sum(1 for r in act_results if r.get("status") == "task_created")
    ctx.log_msg(f"Verify: {tasks_created} tasks created for issues")
    return {"tasks_created": tasks_created, "total_issues": len(act_results)}


# === Builder ===

def orient_builder(ctx: AgentContext) -> dict:
    """Builder: конкретная задача — уходит в настоящее планирование
    реализации (см. _build_directed). Без задачи — прежний обход
    todo/in_progress задач (плановый прогон, не директива).

    23.08.2026: раньше при любом вызове Строитель просто помечал задачу
    статусом «в работе» и добавлял узел графа — кода не писал и не
    предлагал никогда, даже по прямой просьбе. Фаундер прямо сказал:
    агенты должны реально работать, не быть трекерами.

    Сознательное ограничение, оставленное намеренно: Строитель НЕ пишет
    файлы в боевом репозитории сам и не коммитит — только предлагает
    конкретный план/патч, который проверяет человек, прежде чем он попадёт
    в код. Это то же правило «безопасность важнее самостоятельности»,
    что уже действует для computer_use.py и подтверждения кликов — не
    новое исключение, а тот же принцип, применённый здесь.
    """
    if ctx.task and ctx.task.strip():
        ctx.log_msg(f"Orient: реальная задача на реализацию — «{ctx.task[:80]}»")
        return {"directed": True}
    tasks = task_svc.list_tasks(status="todo")
    in_progress = task_svc.list_tasks(status="in_progress")
    ctx.log_msg(f"Orient: {len(tasks)} todo tasks, {len(in_progress)} in progress")
    return {"directed": False, "todo": len(tasks), "in_progress": len(in_progress), "tasks": [t.model_dump() for t in tasks[:5]]}


def observe_builder(ctx: AgentContext, orient_data: dict) -> list:
    """Builder: при директиве — сама задача. Иначе — задачи со словами
    build/create/implement в названии, как раньше."""
    if orient_data.get("directed"):
        return [{"directed": True, "task": ctx.task}]
    buildable = []
    for t in orient_data.get("tasks", []):
        if "build" in t["title"].lower() or "create" in t["title"].lower() or "implement" in t["title"].lower():
            buildable.append(t)
    ctx.log_msg(f"Observe: {len(buildable)} buildable tasks found")
    return buildable


def think_builder(ctx: AgentContext, items: list) -> list[dict]:
    """Builder: Plan build steps — или одна директива на реализацию."""
    if items and items[0].get("directed"):
        return [{"action": "build_directed", "task": items[0]["task"]}]
    actions = []
    for t in items:
        actions.append({
            "action": "build",
            "task_id": t["id"],
            "title": t["title"],
            "plan": f"Implement: {t['title']}",
        })
    ctx.log_msg(f"Think: planned {len(actions)} builds")
    return actions


def _build_directed(ctx: AgentContext, task: str) -> dict:
    """Настоящий план реализации моделью — не пишет и не коммитит код сам
    (см. пояснение в orient_builder), только предлагает конкретный план,
    который человек проверяет и применяет сам."""
    import asyncio

    from .llm import LLMService
    from ..core.config import settings

    llm = LLMService(provider="deepseek", model="deepseek-chat", api_key=settings.deepseek_api_key)
    prompt = (
        f"Задача на реализацию: {task}\n\n"
        "Предложи конкретный план: какие файлы, скорее всего, нужно тронуть, "
        "какие функции/модули завести или поменять, в каком порядке. Если "
        "уместно — короткий фрагмент кода как иллюстрация, не полный файл. "
        "Не выдумывай точные пути файлов, если не уверен — скажи, что нужно "
        "уточнить структуру проекта. Это ПРЕДЛОЖЕНИЕ для человека, не "
        "выполненная работа — не пиши так, будто уже сделал."
    )
    try:
        plan = asyncio.run(llm.generate_response(prompt, kind=budget.BACKGROUND)).strip()
    except Exception as e:
        ctx.log_msg(f"Act: план не удался — {e}")
        return {"status": "error", "task": task, "error": str(e)}

    for line in plan.splitlines():
        if line.strip():
            ctx.log_msg(line.strip())

    from . import memory as mem_svc

    fact = mem_svc.add_fact(
        content=f"Предложенный план реализации «{task[:200]}»: {plan}",
        source="builder",
        confidence=0.5,  # план, не факт — достоверность ниже находок Исследователя/Рецензента
    )
    ctx.log_msg(f"Act: план записан в память ({fact.id}), ждёт вашей проверки")
    return {"status": "proposed", "task": task, "plan": plan, "fact_id": fact.id}


def act_builder(ctx: AgentContext, actions: list[dict]) -> list[dict]:
    """Builder: реальный план реализации по директиве, иначе — помечает
    задачи «в работе» и заводит узел графа, как раньше."""
    results = []
    for action in actions:
        if action["action"] == "build_directed":
            results.append(_build_directed(ctx, action["task"]))
        elif action["action"] == "build":
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
    """Builder: Verify builds — или итог настоящего планирования."""
    proposed = [r for r in act_results if r.get("status") == "proposed"]
    if proposed:
        ctx.log_msg(f"Verify: план готов — {proposed[0]['plan'][:120]}")
        return {"status": "proposed", "plan": proposed[0]["plan"], "fact_id": proposed[0]["fact_id"]}
    started = sum(1 for r in act_results if r["status"] == "started")
    ctx.log_msg(f"Verify: {started} builds started")
    return {"builds_started": started}


# === Researcher ===

def orient_researcher(ctx: AgentContext) -> dict:
    """Researcher: конкретный запрос — уходит в настоящее исследование
    (веб-поиск + синтез, см. _research_directed ниже). Без запроса —
    прежний автономный обход графа на предмет слабо связанных узлов
    (плановый прогон, не директива фаундера/Джарвиса).

    23.08.2026: раньше эта роль ВСЕГДА делала обход графа и игнорировала
    переданную задачу (ctx.task) целиком — даже при вызове с конкретным
    вопросом «разберись, почему X» реального исследования не происходило,
    только создавалась ещё одна задача «кто-то пусть исследует». Фаундер
    прямо сказал: агенты должны реально работать, не быть трекерами.
    """
    if ctx.task and ctx.task.strip():
        ctx.log_msg(f"Orient: реальный запрос — «{ctx.task[:80]}»")
        return {"directed": True}
    stats = graph_svc.get_stats()
    from . import memory as mem_svc
    mem_stats = mem_svc.get_stats()
    active = mem_stats.get('active', 0)
    ctx.log_msg(f"Orient: graph has {stats.nodes} nodes, memory has {active} active facts")
    return {"directed": False, "graph": stats.model_dump(), "memory": mem_stats}


def observe_researcher(ctx: AgentContext, orient_data: dict) -> list:
    """Researcher: при директиве — сама задача, единственный пункт. Иначе —
    слабо связанные узлы графа, как раньше."""
    if orient_data.get("directed"):
        return [{"directed": True, "query": ctx.task}]
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


def think_researcher(ctx: AgentContext, items: list) -> list[dict]:
    """Researcher: Plan research tasks — или одно направленное действие."""
    if items and items[0].get("directed"):
        return [{"action": "research_directed", "query": items[0]["query"]}]
    actions = []
    for node in items:
        actions.append({
            "action": "research",
            "node_id": node["id"],
            "label": node["label"],
            "connections": node["connections"],
        })
    ctx.log_msg(f"Think: {len(actions)} research tasks planned")
    return actions


def _research_directed(ctx: AgentContext, query: str) -> dict:
    """Настоящее исследование: веб-поиск + синтез моделью, результат кладём
    в память фактом — не заводим ещё одну задачу «кто-то пусть посмотрит»."""
    import asyncio

    from . import websearch
    from .llm import LLMService
    from ..core.config import settings

    if not websearch.is_configured():
        ctx.log_msg("Act: веб-поиск не настроен (нет FIRECRAWL_API_KEY) — не могу исследовать по-настоящему")
        return {"status": "unavailable", "query": query, "reason": "web_search не настроен"}

    try:
        search_results = asyncio.run(websearch.run_tool({"query": query}))
    except Exception as e:
        ctx.log_msg(f"Act: веб-поиск не удался — {e}")
        return {"status": "error", "query": query, "error": str(e)}

    llm = LLMService(provider="deepseek", model="deepseek-chat", api_key=settings.deepseek_api_key)
    prompt = (
        f"Вопрос: {query}\n\nНайденные источники:\n{search_results}\n\n"
        "Дай короткий фактический ответ на вопрос по источникам выше — "
        "3-6 предложений, с конкретными цифрами/фактами, если они есть. "
        "Если источники не отвечают на вопрос — скажи это прямо, не выдумывай."
    )
    try:
        finding = asyncio.run(llm.generate_response(prompt, kind=budget.BACKGROUND)).strip()
    except Exception as e:
        ctx.log_msg(f"Act: синтез находки не удался — {e}")
        return {"status": "error", "query": query, "error": str(e)}

    from . import memory as mem_svc

    fact = mem_svc.add_fact(
        content=f"Исследование «{query}»: {finding}",
        source="researcher",
        confidence=0.6,
    )
    ctx.log_msg(f"Act: находка записана в память ({fact.id})")
    return {"status": "found", "query": query, "finding": finding, "fact_id": fact.id}


def act_researcher(ctx: AgentContext, actions: list[dict]) -> list[dict]:
    """Researcher: реальное исследование по директиве, иначе — заводит
    задачи по слабо связанным узлам графа, как раньше."""
    results = []
    for action in actions:
        if action["action"] == "research_directed":
            results.append(_research_directed(ctx, action["query"]))
        elif action["action"] == "research":
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
    """Researcher: Summarize research plan — или итог настоящего исследования."""
    found = [r for r in act_results if r.get("status") == "found"]
    if found:
        ctx.log_msg(f"Verify: находка готова — {found[0]['finding'][:120]}")
        return {"status": "found", "finding": found[0]["finding"], "fact_id": found[0]["fact_id"]}
    tasks_created = sum(1 for r in act_results if r.get("status") == "task_created")
    ctx.log_msg(f"Verify: {tasks_created} research tasks created")
    return {"research_tasks": tasks_created}


# === Curator ===

def orient_curator(ctx: AgentContext) -> dict:
    """Куратор: сколько всего в памяти и сколько уже в архиве."""
    from . import curator as curator_svc

    stats = curator_svc.get_stats()
    mem = stats["memory"]
    ctx.log_msg(
        f"Orient: {mem.get('active', 0)} активных фактов, "
        f"{stats['archived']} в архиве"
    )
    return stats


def observe_curator(ctx: AgentContext, orient_data: dict) -> list:
    """Куратор: что именно требует уборки."""
    from . import curator as curator_svc

    report = curator_svc.run_cycle(apply=False)
    findings = []
    if report["duplicates"]["facts"]:
        findings.append({"kind": "duplicates", "count": report["duplicates"]["facts"]})
    if report["decay"]["facts"]:
        findings.append({"kind": "decay", "count": report["decay"]["facts"]})
    if report["junk"]["facts"]:
        findings.append({"kind": "junk", "count": report["junk"]["facts"]})

    ctx.log_msg(f"Observe: найдено {len(findings)} видов беспорядка")
    return findings


def think_curator(ctx: AgentContext, findings: list) -> list[dict]:
    """Куратор: решает, что делать — и ничего не удаляет.

    Дубли и старение применяются сами: они обратимы. Архивация мусора
    уходит человеку задачей, потому что вынимает записи из памяти.
    """
    actions = []
    for finding in findings:
        if finding["kind"] in ("duplicates", "decay"):
            actions.append({"action": f"apply_{finding['kind']}", "count": finding["count"]})
        elif finding["kind"] == "junk":
            actions.append({"action": "propose_archive", "count": finding["count"]})

    ctx.log_msg(f"Think: {len(actions)} действий запланировано")
    return actions


def act_curator(ctx: AgentContext, actions: list[dict]) -> list[dict]:
    """Куратор: применяет обратимое, спорное отдаёт человеку."""
    from . import curator as curator_svc

    results = []
    for action in actions:
        kind = action["action"]
        try:
            if kind == "apply_duplicates":
                merged = curator_svc.merge_duplicates()
                results.append({"action": kind, "status": "ok", "merged": merged})
                ctx.log_msg(f"Act: склеено дублей — {merged}")

            elif kind == "apply_decay":
                changed = curator_svc.apply_decay()
                results.append({"action": kind, "status": "ok", "changed": changed})
                ctx.log_msg(f"Act: понижена достоверность у {changed} фактов")

            elif kind == "propose_archive":
                task = task_svc.create_task(task_svc.TaskCreate(
                    title=f"Архивировать мусор в памяти: {action['count']} записей",
                    description=(
                        "Куратор нашёл пустые и обрывочные записи. Архивация вынимает "
                        "их из памяти, поэтому нужно твоё подтверждение. Вернуть можно "
                        "в любой момент через /api/curator/restore."
                    ),
                    assigned_agent="curator",
                    tags=["память", "уборка"],
                ))
                results.append({"action": kind, "status": "task_created", "task_id": task.id})
                ctx.log_msg(f"Act: архивация {action['count']} записей вынесена на подтверждение")
        except Exception as e:
            results.append({"action": kind, "status": "error", "error": str(e)})
    return results


def verify_curator(ctx: AgentContext, act_results: list[dict]) -> dict:
    """Куратор: итог прохода."""
    merged = sum(r.get("merged", 0) for r in act_results)
    decayed = sum(r.get("changed", 0) for r in act_results)
    proposed = sum(1 for r in act_results if r.get("status") == "task_created")
    ctx.log_msg(f"Verify: склеено {merged}, состарено {decayed}, на подтверждении {proposed}")
    return {"merged": merged, "decayed": decayed, "proposed": proposed, "deleted": 0}


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


JARVIS_AGENTS = {
    "librarian": "связывает документы, наводит порядок в графе знаний",
    "reviewer": "проверяет качество, ищет несвязанные и подозрительные узлы",
    "builder": "делает: пишет, собирает, реализует",
    "researcher": "изучает вопрос, собирает данные и источники",
    "monitor": "следит за здоровьем системы и застрявшими задачами",
    "curator": "наводит порядок в памяти: дубли, устаревшее, мусор — не удаляя",
}

_JARVIS_PROMPT = """Ты Jarvis, оркестратор Nexus OS. Твоя работа — решить,
кто из агентов возьмёт каждую задачу, и объяснить почему.

Состояние системы:
{state}

Что известно из памяти:
{memory}

Задачи, требующие внимания:
{tasks}

Агенты:
{agents}

Для каждой задачи выбери исполнителя и коротко обоснуй выбор — по сути
задачи, а не по формальным признакам. Если задача бессмысленна или
дублирует другую, поставь assign_to: null и объясни.

Верни СТРОГО JSON:
{{"decisions": [{{"task_id": "...", "assign_to": "librarian|reviewer|builder|researcher|monitor|null", "reason": "..."}}],
  "summary": "одно предложение: что происходит в системе"}}"""


def _think_jarvis_fallback(critical_tasks: list) -> list[dict]:
    """Запасной маршрут по тегам — когда модель недоступна или без бюджета."""
    actions = []
    for t in critical_tasks:
        assigned = "librarian"
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
            "reason": "маршрут по тегам (LLM недоступен)",
        })
    return actions


def think_jarvis(ctx: AgentContext, critical_tasks: list) -> list[dict]:
    """Jarvis: решает, кто возьмёт задачу — рассуждением, а не по тегам.

    Раньше здесь был if/elif по тегам: «review» → reviewer и так далее.
    Это не мышление, а таблица маршрутизации. Теперь решение принимает
    модель, глядя на состояние системы и память, и обязана обосновать
    выбор — обоснование ложится в память (I-6).
    """
    if not critical_tasks:
        ctx.log_msg("Think: задач, требующих внимания, нет")
        return []

    try:
        actions, summary = _think_with_llm(ctx, critical_tasks)
    except budget.BudgetExceeded as e:
        ctx.log_msg(f"Think: бюджет исчерпан ({e}) — маршрут по тегам")
        return _think_jarvis_fallback(critical_tasks)
    except Exception as e:
        logger.warning("Jarvis не смог подумать через LLM: %s", e)
        ctx.log_msg("Think: LLM недоступен — маршрут по тегам")
        return _think_jarvis_fallback(critical_tasks)

    ctx.log_msg(f"Think: {len(actions)} решений — {summary}")
    return actions


def _think_with_llm(ctx: AgentContext, critical_tasks: list) -> tuple[list[dict], str]:
    """Собирает контекст, спрашивает модель, разбирает решения."""
    import asyncio
    import json

    from . import memory as mem_svc
    from .llm import LLMService
    from ..core.config import settings

    stats = graph_svc.get_stats()
    all_tasks = task_svc.list_tasks()
    titles = " ".join(t.get("title", "") for t in critical_tasks)
    facts = mem_svc.recall(titles, limit=5) if titles.strip() else []

    state = (
        f"Граф: {stats.nodes} узлов, {stats.edges} связей. "
        f"Задач всего: {len(all_tasks)}."
    )
    memory_block = "\n".join(f"- {f.content[:200]}" for f in facts) or "пока ничего"
    tasks_block = "\n".join(
        f"- id={t['id']} | {t['title']} | приоритет {t.get('priority')} | теги {t.get('tags')}"
        for t in critical_tasks
    )
    agents_block = "\n".join(f"- {name}: {what}" for name, what in JARVIS_AGENTS.items())

    prompt = _JARVIS_PROMPT.format(
        state=state, memory=memory_block, tasks=tasks_block, agents=agents_block
    )

    # 23.08.2026: найдено при работе над Content Factory — LLMService() без
    # аргументов берёт NEXSYS_LLM_PROVIDER=ollama из .env, а локальный
    # Ollama на машине не поднят. Реальные персоны сидят на deepseek-chat
    # с DEEPSEEK_API_KEY — этот вызов молча падал в except ниже и уходил в
    # маршрут по тегам всегда, «умная» LLM-маршрутизация Джарвиса ни разу
    # реально не срабатывала.
    llm = LLMService(provider="deepseek", model="deepseek-chat", api_key=settings.deepseek_api_key)
    raw = asyncio.run(llm.generate_response(prompt, kind=budget.BACKGROUND, json_mode=True))

    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start : end + 1]
    data = json.loads(text)

    known_ids = {t["id"] for t in critical_tasks}
    titles_by_id = {t["id"]: t["title"] for t in critical_tasks}

    actions = []
    for d in data.get("decisions", []):
        task_id = str(d.get("task_id", ""))
        assign_to = d.get("assign_to")
        # Модель может выдумать id задачи или несуществующего агента
        if task_id not in known_ids:
            continue
        if assign_to not in JARVIS_AGENTS:
            ctx.log_msg(f"Think: задача {task_id} оставлена без исполнителя")
            continue
        actions.append({
            "action": "delegate",
            "task_id": task_id,
            "title": titles_by_id[task_id],
            "assign_to": assign_to,
            "reason": str(d.get("reason", ""))[:300],
        })

    return actions, str(data.get("summary", ""))[:200]


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
    AgentRole.CURATOR: {
        "orient": orient_curator,
        "observe": observe_curator,
        "think": think_curator,
        "act": act_curator,
        "verify": verify_curator,
    },
    AgentRole.JARVIS: {
        "orient": orient_jarvis,
        "observe": observe_jarvis,
        "think": think_jarvis,
        "act": act_jarvis,
        "verify": verify_jarvis,
    },
}


def _remember_run(agent: Agent, task: str, actions, verify_result, cost_usd: float) -> None:
    """Кладёт итог прогона в память — иначе агент ничего о себе не помнит (I-6).

    Пишем обоснования решений, а не сухую статистику: именно они пригодятся
    завтра, когда придётся понять, почему система поступила так.
    """
    from . import memory as mem_svc

    try:
        lines = [f"Прогон агента {agent.name} ({agent.role.value}). Задача: {task}"]
        for a in actions if isinstance(actions, list) else []:
            reason = a.get("reason")
            if reason:
                lines.append(f"- {a.get('title', a.get('task_id', ''))} → "
                             f"{a.get('assign_to', '?')}: {reason}")
        lines.append(f"Итог: {verify_result}")
        if cost_usd:
            lines.append(f"Стоимость прогона: ${cost_usd}")

        mem_svc.add_fact(
            "\n".join(lines),
            layer=mem_svc.MemoryLayer.INBOX,
            source=f"agent:{agent.id}",
            tags=["agent-run", agent.role.value],
        )
    except Exception:
        logger.warning("Не удалось записать прогон агента в память", exc_info=True)


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

    spent_before = budget.spent_today()
    eventbus.emit(
        eventbus.AGENT_RUN_STARTED,
        {"agent_id": agent.id, "trigger": (context or {}).get("trigger", "manual")},
        source=eventbus.SOURCE_JARVIS,
    )

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

        cost = round(budget.spent_today() - spent_before, 6)
        _remember_run(agent, task, actions, verify_result, cost)
        eventbus.emit(
            eventbus.AGENT_RUN_FINISHED,
            {
                "agent_id": agent.id,
                "trigger": (context or {}).get("trigger", "manual"),
                "summary": str(verify_result)[:200],
                "cost_usd": cost,
            },
            source=eventbus.SOURCE_JARVIS,
        )

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
