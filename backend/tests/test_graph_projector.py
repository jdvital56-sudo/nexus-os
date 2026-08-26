"""Проекция всех хранилищ во «Второй мозг».

Фаундер попросил 26.08.2026: «надо, чтобы второй мозг видел абсолютно
всё». До этого граф видел документы, заметки Obsidian, сущности из
разговора, календарь, скиллы и агентов — но **не видел** задачи, идеи,
контент-завод, память, находки трендов и подписки. То есть половину того,
чем система реально живёт.

Собрано одним местом, а не размазано по шести сервисам: каждый из них
дёргал бы граф сам, и связь «хранилище знает про граф» протянулась бы
через весь код. Проектор читает хранилища и раскладывает их в граф — знать
про него должен он один.
"""
import pytest

from backend.services import graph as graph_svc
from backend.services import graph_projector as gp
from backend.services import ideas as ideas_svc
from backend.services import tasks as task_svc
from backend.models.schemas import IdeaCreate, TaskCreate


def _node_ids() -> set[str]:
    return {n.id for n in graph_svc.list_nodes(limit=500)}


# === Задачи ===

def test_tasks_land_in_graph():
    task_svc.create_task(TaskCreate(title="Оплатить Hetzner", tags=["деньги"]))
    gp.project_all()
    assert any(i.startswith("task:") for i in _node_ids())


def test_task_keeps_its_title():
    t = task_svc.create_task(TaskCreate(title="Позвонить клиенту"))
    gp.project_all()
    node = graph_svc.get_node(f"task:{t.id}")
    assert "Позвонить клиенту" in node.label


# === Идеи ===

def test_ideas_land_in_graph():
    ideas_svc.create_idea(IdeaCreate(content="Сводка дня в девять вечера"))
    gp.project_all()
    assert any(i.startswith("idea:") for i in _node_ids())


def test_system_idea_is_marked_as_such():
    """Видно, кто предложил: фаундер или Джарвис — иначе граф врёт про
    происхождение мысли."""
    idea = ideas_svc.propose("Тренд про осознанность")
    gp.project_all()
    node = graph_svc.get_node(f"idea:{idea.id}")
    assert node.metadata.get("source") == "system"


# === Повторный прогон ===

def test_second_run_does_not_duplicate():
    """Джоба идёт каждый час — граф не должен пухнуть копиями."""
    task_svc.create_task(TaskCreate(title="Один раз"))
    gp.project_all()
    first = len(_node_ids())
    gp.project_all()
    assert len(_node_ids()) == first


def test_changed_task_updates_its_node():
    from backend.models.schemas import TaskUpdate, TaskStatus

    t = task_svc.create_task(TaskCreate(title="Было"))
    gp.project_all()
    task_svc.update_task(t.id, TaskUpdate(status=TaskStatus.DONE))
    gp.project_all()

    node = graph_svc.get_node(f"task:{t.id}")
    assert node.metadata.get("status") == "done"


# === Устойчивость ===

def test_broken_store_does_not_stop_the_rest(monkeypatch):
    """Одно упавшее хранилище не должно оставить граф без всех остальных."""
    def boom(*a, **kw):
        raise RuntimeError("хранилище недоступно")

    # Патчим сам модуль задач: проектор импортирует его лениво внутри
    # функции (так во всём проекте, против циклических импортов).
    monkeypatch.setattr(task_svc, "list_tasks", boom)
    ideas_svc.create_idea(IdeaCreate(content="Уцелевшая идея"))

    stats = gp.project_all()

    assert stats["ideas"] >= 1
    assert "tasks" in stats["failed"]


def test_empty_stores_are_not_an_error():
    stats = gp.project_all()
    assert isinstance(stats, dict)
    assert stats["failed"] == []


# === Связи, ради которых граф и нужен ===

@pytest.mark.asyncio
async def test_content_links_to_the_idea_it_came_from():
    """«Сделать контент по идее» — эта связь и есть ценность графа:
    видно, из какой мысли выросла публикация."""
    from backend.services import content_factory as cf

    class StubLLM:
        async def generate_response(self, user_message, context="", kind="interactive", json_mode=False):
            return '[{"hook": "Х", "script": "С", "caption": "П", "hashtags": []}]'

    idea = ideas_svc.create_idea(IdeaCreate(content="осознанность в спа"))
    items = await cf.generate_plan("осознанность в спа", count=1, llm=StubLLM())
    gp.project_all()

    edges = graph_svc.list_edges(limit=500)
    pair = {(e.source, e.target) for e in edges}
    assert (f"idea:{idea.id}", f"content:{items[0].id}") in pair
