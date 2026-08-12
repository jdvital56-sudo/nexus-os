"""Тесты извлечения сущностей из диалога в граф (PR-7)."""
import json

import pytest

from backend.services import budget
from backend.services import entity_extraction as ex
from backend.services import graph as graph_svc


class JsonLLM:
    """Отдаёт заранее заданный ответ и помнит, каким kind её звали."""

    def __init__(self, payload, wrap: str = "plain"):
        self.payload = payload
        self.wrap = wrap
        self.kinds: list[str] = []

    async def generate_response(self, user_message: str, context: str = "", kind: str = "interactive", json_mode: bool = False) -> str:
        self.kinds.append(kind)
        body = json.dumps(self.payload, ensure_ascii=False)
        if self.wrap == "fence":
            return f"Вот результат:\n```json\n{body}\n```"
        if self.wrap == "chatty":
            return f"Конечно! {body} Надеюсь, помог."
        return body


SIMPLE = {
    "entities": [
        {"name": "Одесса", "type": "concept"},
        {"name": "Nexus OS", "type": "concept"},
    ],
    "relations": [{"source": "Nexus OS", "target": "Одесса", "kind": "related"}],
}


def test_slug_normalises_case_and_spaces():
    assert ex._node_id("  Nexus   OS ") == ex._node_id("nexus os")


def test_parse_plain_json():
    assert len(ex._parse(json.dumps(SIMPLE, ensure_ascii=False))["entities"]) == 2


def test_parse_markdown_fence():
    raw = f"```json\n{json.dumps(SIMPLE, ensure_ascii=False)}\n```"
    assert len(ex._parse(raw)["entities"]) == 2


def test_parse_surrounding_chatter():
    raw = f"Конечно! {json.dumps(SIMPLE, ensure_ascii=False)} Готово."
    assert len(ex._parse(raw)["entities"]) == 2


def test_parse_garbage_is_survivable():
    assert ex._parse("я не смог разобрать") == {"entities": [], "relations": []}


def test_parse_drops_entities_without_name():
    raw = json.dumps({"entities": [{"type": "concept"}, {"name": "Хорошая"}], "relations": []})
    assert [e["name"] for e in ex._parse(raw)["entities"]] == ["Хорошая"]


def test_upsert_creates_nodes_and_edges():
    result = ex.upsert(SIMPLE, source="telegram:42", semantic=False)

    assert result == {"nodes_added": 2, "edges_added": 1, "edges_dropped": 0}
    labels = [n.label for n in graph_svc.list_nodes()]
    assert "Одесса" in labels
    assert "Nexus OS" in labels


def test_same_entity_is_not_duplicated():
    ex.upsert(SIMPLE, source="telegram:42", semantic=False)
    second = ex.upsert(
        {"entities": [{"name": "  ОДЕССА  ", "type": "concept"}], "relations": []},
        source="telegram:42",
        semantic=False,
    )

    assert second["nodes_added"] == 0
    assert len([n for n in graph_svc.list_nodes() if n.label.lower().strip() == "одесса"]) == 1


def test_unknown_type_falls_back_to_concept():
    ex.upsert(
        {"entities": [{"name": "Штука", "type": "выдуманный-тип"}], "relations": []},
        source="s",
        semantic=False,
    )
    node = graph_svc.get_node(ex._node_id("Штука"))
    assert node.node_type.value == "concept"


def test_self_referencing_relation_is_skipped():
    result = ex.upsert(
        {
            "entities": [{"name": "Один", "type": "concept"}],
            "relations": [{"source": "Один", "target": "Один", "kind": "related"}],
        },
        source="s",
        semantic=False,
    )
    assert result["edges_added"] == 0


def test_relation_to_unknown_entity_is_skipped():
    result = ex.upsert(
        {
            "entities": [{"name": "Один", "type": "concept"}],
            "relations": [{"source": "Один", "target": "Неизвестный", "kind": "related"}],
        },
        source="s",
        semantic=False,
    )
    assert result["edges_added"] == 0


@pytest.mark.asyncio
async def test_extraction_is_a_background_call():
    """Извлечение — фоновая нагрузка, её бюджет обязан глушить (I-4)."""
    llm = JsonLLM(SIMPLE)

    await ex.extract_from_dialog(llm, "текст", "ответ", source="telegram:42", semantic=False)

    assert llm.kinds == [budget.BACKGROUND]


@pytest.mark.asyncio
async def test_extraction_fills_graph_end_to_end():
    llm = JsonLLM(SIMPLE, wrap="fence")

    result = await ex.extract_from_dialog(
        llm, "переезжаю в Одессу", "понял", source="telegram:42", semantic=False
    )

    assert result["nodes_added"] == 2
    assert result["edges_added"] == 1


@pytest.mark.asyncio
async def test_empty_extraction_does_not_touch_graph():
    llm = JsonLLM({"entities": [], "relations": []})

    result = await ex.extract_from_dialog(llm, "привет", "привет", source="s", semantic=False)

    assert result == {"nodes_added": 0, "edges_added": 0, "edges_dropped": 0}
    assert graph_svc.list_nodes() == []


# --- Связи, которые терялись вживую (найдено 2026-08-12) ---


def test_relation_matches_entity_written_in_another_case():
    """Модель пишет «Nexus OS» в entities и «nexus os» в relations —
    из-за регистра связь пропадала, и граф оставался россыпью точек."""
    result = ex.upsert(
        {
            "entities": [{"name": "Nexus OS", "type": "concept"},
                         {"name": "Одесса", "type": "concept"}],
            "relations": [{"source": "nexus os", "target": "  ОДЕССА ", "kind": "related"}],
        },
        source="s",
        semantic=False,
    )
    assert result["edges_added"] == 1


def test_relation_can_reach_entity_from_earlier_dialogs():
    """Сущность из прошлого разговора уже в графе — связь с ней законна."""
    ex.upsert({"entities": [{"name": "Одесса", "type": "concept"}], "relations": []},
              source="s", semantic=False)

    result = ex.upsert(
        {
            "entities": [{"name": "Спа-оффер", "type": "concept"}],
            "relations": [{"source": "Спа-оффер", "target": "Одесса", "kind": "related"}],
        },
        source="s",
        semantic=False,
    )
    assert result["edges_added"] == 1


def test_relation_through_the_user_is_dropped_and_counted():
    """Живой DeepSeek связывал всё через «Пользователь», которого нет
    среди сущностей — все связи молча исчезали."""
    result = ex.upsert(
        {
            "entities": [{"name": "Nexus OS", "type": "concept"},
                         {"name": "PropFlow", "type": "concept"}],
            "relations": [
                {"source": "Пользователь", "target": "Nexus OS", "kind": "related"},
                {"source": "Пользователь", "target": "PropFlow", "kind": "related"},
            ],
        },
        source="telegram:42",
        semantic=False,
    )
    assert result["edges_added"] == 0
    assert result["edges_dropped"] == 2


def test_prompt_forbids_dragging_the_speakers_into_relations():
    assert "Пользователь" in ex._PROMPT
    assert "только между сущностями" in ex._PROMPT
