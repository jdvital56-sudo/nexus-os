"""Fireflies integration — parse call transcripts into memory.

Flow: transcript → extract key points → create memory facts → link to graph.
Works with raw text transcripts (manual paste or API).
"""
import re
from datetime import datetime
from typing import Any
from ..models.schemas import DocumentCreate, DocType, GraphNode, GraphEdge, NodeType, EdgeType
from . import documents as doc_svc
from . import graph as graph_svc
from . import memory as mem_svc
from .tagger import generate_tags, extract_keywords


def parse_transcript(text: str) -> dict:
    """Parse a call transcript into structured data.

    Extracts: speakers, key points, action items, decisions, questions.
    Works with formats like:
    - "Speaker: text"
    - "[HH:MM] Speaker: text"
    - "- Speaker: text"
    """
    lines = text.strip().split("\n")
    speakers: dict[str, int] = {}
    key_points: list[str] = []
    action_items: list[str] = []
    decisions: list[str] = []

    current_speaker = None
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try to extract speaker
        speaker_match = re.match(r'(?:\[.*?\]\s*)?([A-Za-zА-Яа-яёЁ][\w\s]+?):\s*(.*)', line)
        if speaker_match:
            current_speaker = speaker_match.group(1).strip()
            content = speaker_match.group(2).strip()
            speakers[current_speaker] = speakers.get(current_speaker, 0) + 1
        else:
            content = line

        content_lower = content.lower()

        # Action items
        if any(marker in content_lower for marker in ["нужно", "надо", "сделать", "todo", "action", "задача", "поручить"]):
            action_items.append(f"[{current_speaker or '?'}] {content}")

        # Decisions
        if any(marker in content_lower for marker in ["решили", "договорились", "принято", "decision", "согласовано", "утверждено"]):
            decisions.append(f"[{current_speaker or '?'}] {content}")

        # Key points (longer statements)
        if len(content) > 50 and current_speaker:
            key_points.append(f"[{current_speaker}] {content}")

    return {
        "speakers": speakers,
        "speaker_count": len(speakers),
        "key_points": key_points[:10],
        "action_items": action_items[:5],
        "decisions": decisions[:5],
        "line_count": len(lines),
    }


def ingest_transcript(
    text: str,
    title: str = "",
    participants: list[str] | None = None,
    auto_memory: bool = True,
) -> dict:
    """Ingest a call transcript into NEXSYS.

    Steps:
    1. Parse transcript
    2. Create document with auto-tagging
    3. Create graph nodes for call + participants
    4. Extract memory facts
    5. Create tasks for action items
    """
    parsed = parse_transcript(text)

    # Default title
    if not title:
        speakers = list(parsed["speakers"].keys())
        title = f"Call: {', '.join(speakers[:3])}" if speakers else f"Call {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"

    # 1. Create document
    doc = doc_svc.create_document(DocumentCreate(
        title=title,
        content=text,
        doc_type=DocType.TEXT,
        tags=["call", "transcript"],
        source="fireflies",
    ), auto_tag=True)

    # 2. Create call node in graph
    call_id = f"call:{doc.id}"
    call_node = GraphNode(
        id=call_id,
        label=title,
        node_type=NodeType.SESSION,
        metadata={
            "source": "fireflies",
            "speaker_count": parsed["speaker_count"],
            "speakers": list(parsed["speakers"].keys()),
            "action_count": len(parsed["action_items"]),
            "decision_count": len(parsed["decisions"]),
        },
    )
    try:
        graph_svc.add_node(call_node)
    except Exception:
        pass

    # 3. Link call to document
    try:
        graph_svc.add_edge(GraphEdge(source=call_id, target=f"doc:{doc.id}", edge_type=EdgeType.CONTAINS))
    except Exception:
        pass

    # 4. Create participant nodes
    all_participants = set(list(parsed["speakers"].keys()) + (participants or []))
    for person in all_participants:
        person_id = f"person:{person.lower().replace(' ', '_')}"
        try:
            graph_svc.add_node(GraphNode(
                id=person_id,
                label=person,
                node_type=NodeType.AGENT,
                metadata={"source": "fireflies", "call_count": 1},
            ))
            graph_svc.add_edge(GraphEdge(source=call_id, target=person_id, edge_type=EdgeType.CREATED_BY))
        except Exception:
            pass

    # 5. Extract memory facts
    memory_facts = []
    if auto_memory:
        for point in parsed["key_points"][:3]:
            fact = mem_svc.add_fact(
                content=point,
                layer=mem_svc.MemoryLayer.OPERATIONAL,
                source=f"call:{doc.id}",
                confidence=0.7,
                ttl_hours=720,  # 30 days
                tags=["call", "transcript"],
            )
            memory_facts.append(fact)

        for decision in parsed["decisions"]:
            fact = mem_svc.add_fact(
                content=decision,
                layer=mem_svc.MemoryLayer.MEMORY,
                source=f"call:{doc.id}",
                confidence=0.9,
                ttl_hours=2160,  # 90 days
                tags=["call", "decision"],
            )
            memory_facts.append(fact)

    # 6. Create tasks for action items
    from . import tasks as task_svc
    tasks_created = []
    for action in parsed["action_items"]:
        try:
            task = task_svc.create_task(task_svc.TaskCreate(
                title=f"[Call] {action[:60]}",
                description=f"From call: {title}\n{action}",
                tags=["call", "action-item"],
            ))
            tasks_created.append(task.id)
        except Exception:
            pass

    return {
        "document_id": doc.id,
        "call_id": call_id,
        "parsed": {
            "speakers": parsed["speakers"],
            "key_points": len(parsed["key_points"]),
            "action_items": len(parsed["action_items"]),
            "decisions": len(parsed["decisions"]),
        },
        "memory_facts_created": len(memory_facts),
        "tasks_created": len(tasks_created),
        "participants": list(all_participants),
    }


def get_call_history(person: str | None = None, limit: int = 20) -> list[dict]:
    """Get call history, optionally filtered by participant."""
    nodes = graph_svc.list_nodes(node_type="session", limit=100)
    calls = []
    for node in nodes:
        if node.metadata.get("source") != "fireflies":
            continue
        if person and person.lower() not in [s.lower() for s in node.metadata.get("speakers", [])]:
            continue
        calls.append({
            "call_id": node.id,
            "label": node.label,
            "speakers": node.metadata.get("speakers", []),
            "action_count": node.metadata.get("action_count", 0),
            "created_at": node.created_at,
        })
    return calls[:limit]
