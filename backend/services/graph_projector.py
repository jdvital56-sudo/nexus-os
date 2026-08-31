"""Проекция всех хранилищ во «Второй мозг».

Фаундер попросил 26.08.2026: «надо, чтобы второй мозг видел абсолютно
всё». Граф видел документы, заметки Obsidian, сущности из разговора,
календарь, скиллы и агентов — но не видел задачи, идеи, контент-завод,
память, направления трендов и подписки, то есть половину живой системы.

**Почему одним местом, а не в каждом сервисе.** Можно было заставить
`tasks.py`, `ideas.py` и остальных дёргать граф при каждой записи. Тогда
шесть хранилищ знали бы про граф, про типы узлов и про формат
идентификаторов — связь, которую потом не разорвать. Здесь наоборот: про
граф знает один проектор, хранилища о нём не подозревают.

Идентификаторы стабильные (`task:<id>`, `idea:<id>`…) — повторный прогон
обновляет узел, а не плодит копию. Джоба идёт каждый час рядом с
синхронизацией Obsidian.
"""
import logging

from ..models.schemas import EdgeType, GraphEdge, GraphNode, NodeType
from . import graph as graph_svc

logger = logging.getLogger(__name__)

# Сколько записей берём из каждого хранилища. Граф — карта, а не свалка:
# тысяча задач в нём не помогает, а связи в ней теряются.
LIMIT = 200

# Длина подписи узла. Длиннее — карта превращается в простыню текста.
LABEL_CHARS = 70


def _label(text: str) -> str:
    text = " ".join(str(text or "").split())
    return text[:LABEL_CHARS] + ("…" if len(text) > LABEL_CHARS else "")


def _put(node_id: str, label: str, node_type: NodeType, meta: dict) -> None:
    """Кладёт или обновляет узел. Граф сам перезаписывает по тому же id."""
    graph_svc.add_node(
        GraphNode(id=node_id, label=_label(label), node_type=node_type, metadata=meta)
    )


def _link(source: str, target: str, kind: EdgeType = EdgeType.RELATED) -> None:
    try:
        graph_svc.add_edge(GraphEdge(source=source, target=target, edge_type=kind))
    except Exception:
        # Ребро без одного из концов — не повод валить весь обход
        logger.debug("Ребро %s -> %s не добавлено", source, target, exc_info=True)


def _project_tasks() -> int:
    from . import tasks as task_svc

    n = 0
    for t in task_svc.list_tasks()[:LIMIT]:
        _put(
            f"task:{t.id}",
            t.title,
            NodeType.TASK,
            {
                "source": "tasks",
                "status": t.status.value,
                "priority": getattr(t.priority, "value", None),
                "tags": list(t.tags or []),
            },
        )
        n += 1
    return n


def _project_ideas() -> int:
    from . import ideas as ideas_svc

    n = 0
    for i in ideas_svc.list_ideas()[:LIMIT]:
        _put(
            f"idea:{i.id}",
            i.content,
            NodeType.CONCEPT,
            {
                "source": i.source.value,  # founder | system — кто придумал
                "status": i.status.value,
                "context": i.context,
            },
        )
        n += 1
    return n


def _project_content() -> int:
    """Черновики контента плюс связь с идеей, из которой они выросли.

    Связь — главная ценность: видно, какая мысль превратилась в публикацию.
    Ищем по тексту идеи в теме черновика: кнопка «сделать контент по идее»
    кладёт содержимое идеи ровно в topic.
    """
    from . import content_factory as cf
    from . import ideas as ideas_svc

    by_text = {" ".join(i.content.lower().split()): i.id for i in ideas_svc.list_ideas()}

    n = 0
    for item in cf.list_items()[:LIMIT]:
        node_id = f"content:{item.id}"
        _put(
            node_id,
            item.caption or item.hook or item.topic,
            NodeType.DOCUMENT,
            {
                "source": "content_factory",
                "status": item.status.value,
                "topic": item.topic,
                "platforms": list(item.platforms or []),
                "scheduled_at": item.scheduled_at,
                "has_media": bool(item.voice_file or item.image_file or item.video_file),
            },
        )
        n += 1

        idea_id = by_text.get(" ".join(item.topic.lower().split()))
        if idea_id:
            _link(f"idea:{idea_id}", node_id, EdgeType.LEADS_TO)
    return n


def _project_memory() -> int:
    from . import memory as memory_svc

    n = 0
    for fact in memory_svc.get_facts(limit=LIMIT):
        _put(
            f"fact:{fact.id}",
            fact.content,
            NodeType.MEMORY,
            {"source": "memory", "layer": getattr(fact.layer, "value", None), "tags": list(fact.tags or [])},
        )
        n += 1
    return n


def _project_directions() -> int:
    """Направления Исследователя — чем фаундер вообще интересуется."""
    from . import researcher

    n = 0
    for d in researcher.get_directions():
        _put(
            f"direction:{d.lower().replace(' ', '-')}",
            d,
            NodeType.CONCEPT,
            {"source": "researcher"},
        )
        n += 1
    return n


def _project_wallet() -> int:
    from . import wallet as wallet_svc

    n = 0
    for s in wallet_svc.list_services()[:LIMIT]:
        sid = s.get("id") if isinstance(s, dict) else getattr(s, "id", None)
        name = s.get("name") if isinstance(s, dict) else getattr(s, "name", "")
        status = s.get("status") if isinstance(s, dict) else getattr(s, "status", "")
        if not sid:
            continue
        _put(
            f"service:{sid}",
            name,
            NodeType.CONCEPT,
            {"source": "wallet", "status": str(status)},
        )
        n += 1
    return n


_SOURCES = {
    "tasks": _project_tasks,
    "ideas": _project_ideas,
    "content": _project_content,
    "memory": _project_memory,
    "directions": _project_directions,
    "wallet": _project_wallet,
}


def project_all() -> dict:
    """Проецирует все хранилища. Упавшее не мешает остальным.

    Возвращает, сколько узлов положено из каждого источника, и список тех,
    что сорвались — молча пропустить нельзя: половина карты выглядела бы
    как «данных просто нет».
    """
    stats: dict = {"failed": []}
    for name, fn in _SOURCES.items():
        try:
            stats[name] = fn()
        except Exception:
            logger.exception("Проекция «%s» в граф сорвалась", name)
            stats[name] = 0
            stats["failed"].append(name)

    total = sum(v for k, v in stats.items() if k != "failed")
    if total:
        logger.info("Второй мозг: спроецировано %d узлов из хранилищ", total)
    return stats
