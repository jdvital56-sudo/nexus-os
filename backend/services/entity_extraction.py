"""Извлечение сущностей и связей из диалога в граф знаний.

Работает фоном после того, как пользователь получил ответ (I-5), и считается
фоновой нагрузкой для дневного бюджета (I-4): если деньги на сегодня кончились,
извлечение просто не происходит — диалог от этого не страдает.
"""
import json
import logging
import re
from typing import Any

from ..models.schemas import EdgeType, GraphEdge, GraphNode, NodeType
from . import budget
from . import graph as graph_svc

logger = logging.getLogger(__name__)

# Выше этого порога считаем, что сущность уже есть в графе под другим написанием
_MERGE_SIMILARITY = 0.93

# Сколько сущностей берём из одного сообщения — защита от простыни
_MAX_ENTITIES = 8

_PROMPT = """Извлеки из диалога сущности и связи между ними.

Сущность — это конкретный человек, компания, проект, продукт, место,
технология или событие. Не извлекай общие слова, местоимения и эмоции.

Верни СТРОГО JSON без пояснений и без markdown:
{{"entities": [{{"name": "...", "type": "..."}}],
  "relations": [{{"source": "...", "target": "...", "kind": "..."}}]}}

type — одно из: concept, document, task, agent, decision, session, file
kind — одно из: related, depends_on, created_by, mentions, contains, leads_to
В relations используй ровно те имена, что в entities.
Если сущностей нет, верни пустые списки.

Диалог:
{dialog}"""


def _slug(name: str) -> str:
    """Нормализует имя в идентификатор — одинаковые сущности дают один узел."""
    slug = re.sub(r"\s+", "-", name.strip().lower())
    slug = re.sub(r"[^\w\-]", "", slug, flags=re.UNICODE)
    return slug.strip("-")


def _node_id(name: str) -> str:
    return f"entity:{_slug(name)}"


def _parse(raw: str) -> dict[str, list[dict]]:
    """Достаёт JSON из ответа модели — та любит обернуть его в ```json."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Модель вернула не JSON, извлечение пропущено")
        return {"entities": [], "relations": []}

    if not isinstance(data, dict):
        return {"entities": [], "relations": []}
    entities = [e for e in data.get("entities", []) if isinstance(e, dict) and e.get("name")]
    relations = [
        r
        for r in data.get("relations", [])
        if isinstance(r, dict) and r.get("source") and r.get("target")
    ]
    return {"entities": entities[:_MAX_ENTITIES], "relations": relations}


def _node_type(value: Any) -> NodeType:
    try:
        return NodeType(str(value).lower())
    except ValueError:
        return NodeType.CONCEPT


def _edge_type(value: Any) -> EdgeType:
    try:
        return EdgeType(str(value).lower())
    except ValueError:
        return EdgeType.RELATED


def _find_similar(name: str) -> str | None:
    """Ищет уже существующий узел с тем же смыслом, но другим написанием."""
    try:
        from .vector_store import search_vectors

        hits = search_vectors(name, limit=3, min_score=_MERGE_SIMILARITY)
    except Exception:
        logger.debug("Семантическое слияние недоступно", exc_info=True)
        return None

    for hit in hits:
        if hit["id"].startswith("graph:"):
            return hit["id"].removeprefix("graph:")
    return None


def _index_node(node_id: str, label: str) -> None:
    try:
        from .vector_store import add_vector

        add_vector(f"graph:{node_id}", label, {"type": "graph"})
    except Exception:
        logger.debug("Не удалось проиндексировать узел %s", node_id, exc_info=True)


def upsert(extracted: dict[str, list[dict]], source: str, semantic: bool = True) -> dict:
    """Кладёт сущности и связи в граф, схлопывая дубли. Возвращает счётчики."""
    resolved: dict[str, str] = {}
    added_nodes = 0

    for entity in extracted.get("entities", []):
        name = str(entity["name"]).strip()
        if not name:
            continue
        node_id = _node_id(name)

        existing = None
        try:
            graph_svc.get_node(node_id)
            existing = node_id
        except Exception:
            if semantic:
                existing = _find_similar(name)

        if existing:
            resolved[name] = existing
            continue

        graph_svc.add_node(
            GraphNode(
                id=node_id,
                label=name,
                node_type=_node_type(entity.get("type")),
                metadata={"source": source, "origin": "dialog"},
            )
        )
        resolved[name] = node_id
        added_nodes += 1
        if semantic:
            _index_node(node_id, name)

    added_edges = 0
    for relation in extracted.get("relations", []):
        src = resolved.get(str(relation["source"]).strip())
        dst = resolved.get(str(relation["target"]).strip())
        if not src or not dst or src == dst:
            continue
        try:
            graph_svc.add_edge(
                GraphEdge(source=src, target=dst, edge_type=_edge_type(relation.get("kind")))
            )
            added_edges += 1
        except Exception:
            logger.debug("Ребро %s -> %s не добавлено", src, dst, exc_info=True)

    return {"nodes_added": added_nodes, "edges_added": added_edges}


async def extract_from_dialog(llm, text: str, reply: str, source: str, semantic: bool = True) -> dict:
    """Полный путь: спросить модель, разобрать ответ, положить в граф.

    Бюджет проверяется здесь, а не только внутри LLMService: задача фоновая
    по своей природе, и это не должно зависеть от того, какой клиент
    подставлен. При исчерпании budget.BudgetExceeded уходит наверх.
    """
    budget.check(budget.BACKGROUND)

    dialog = f"Пользователь: {text}\nАссистент: {reply}"
    raw = await llm.generate_response(
        _PROMPT.format(dialog=dialog), kind=budget.BACKGROUND, json_mode=True
    )
    extracted = _parse(raw)
    if not extracted["entities"]:
        return {"nodes_added": 0, "edges_added": 0}
    return upsert(extracted, source=source, semantic=semantic)
