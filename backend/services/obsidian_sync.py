"""Obsidian vault sync — import notes into knowledge graph.

Reads .md files from an Obsidian vault, extracts wikilinks [[...]] and tags #tag,
builds a graph of interconnected notes.
"""
import re
import json
from pathlib import Path
from datetime import datetime
from ..core.config import DATA_DIR, ensure_data_dir
from ..models.schemas import DocumentCreate, DocType, GraphNode, GraphEdge, NodeType, EdgeType
from . import documents as doc_svc
from . import graph as graph_svc


SYNC_STATE_FILE = DATA_DIR / "obsidian_sync_state.json"


def _load_sync_state() -> dict:
    ensure_data_dir()
    if SYNC_STATE_FILE.exists():
        return json.loads(SYNC_STATE_FILE.read_text())
    return {"synced_files": {}, "last_sync": None}


def _save_sync_state(state: dict):
    ensure_data_dir()
    state["last_sync"] = datetime.utcnow().isoformat()
    SYNC_STATE_FILE.write_text(json.dumps(state, indent=2))


def scan_vault(vault_path: str) -> dict:
    """Scan an Obsidian vault and return statistics."""
    p = Path(vault_path)
    if not p.is_dir():
        raise FileNotFoundError(f"Vault not found: {vault_path}")

    md_files = list(p.glob("**/*.md"))
    total_notes = len(md_files)
    total_words = 0
    tags_found: dict[str, int] = {}
    wikilinks_found: dict[str, int] = {}

    for md in md_files:
        content = md.read_text(encoding="utf-8", errors="replace")
        total_words += len(content.split())

        # Extract tags
        for tag in re.findall(r'(?:^|\s)#([a-zA-Zа-яА-ЯёЁ][\w-]*)', content):
            tags_found[tag] = tags_found.get(tag, 0) + 1

        # Extract wikilinks
        for link in re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', content):
            wikilinks_found[link] = wikilinks_found.get(link, 0) + 1

    return {
        "vault_path": str(p),
        "total_notes": total_notes,
        "total_words": total_words,
        "unique_tags": len(tags_found),
        "unique_wikilinks": len(wikilinks_found),
        "top_tags": sorted(tags_found.items(), key=lambda x: -x[1])[:10],
        "top_links": sorted(wikilinks_found.items(), key=lambda x: -x[1])[:10],
    }


def sync_vault(vault_path: str, incremental: bool = True) -> dict:
    """Sync Obsidian vault to NEXSYS knowledge graph.

    Args:
        vault_path: Path to Obsidian vault directory
        incremental: If True, only process new/modified files

    Returns:
        Sync results with counts.
    """
    p = Path(vault_path)
    if not p.is_dir():
        raise FileNotFoundError(f"Vault not found: {vault_path}")

    state = _load_sync_state()
    synced = state.get("synced_files", {})

    md_files = sorted(p.glob("**/*.md"))
    imported = 0
    skipped = 0
    graph_nodes = 0
    graph_edges = 0

    for md_file in md_files:
        file_key = str(md_file)
        mtime = md_file.stat().st_mtime

        # Skip if already synced and unchanged
        if incremental and file_key in synced and synced[file_key].get("mtime") == mtime:
            skipped += 1
            continue

        content = md_file.read_text(encoding="utf-8", errors="replace")
        title = md_file.stem.replace("-", " ").replace("_", " ").title()

        # Extract tags and links
        tags = list(set(re.findall(r'(?:^|\s)#([a-zA-Zа-яА-ЯёЁ][\w-]*)', content)))
        wikilinks = list(set(re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', content)))

        # Create document
        doc = doc_svc.create_document(DocumentCreate(
            title=title,
            content=content,
            doc_type=DocType.MARKDOWN,
            tags=tags,
            source=f"obsidian:{file_key}",
        ), auto_tag=True)
        imported += 1

        # Create graph node for the note
        note_node = GraphNode(
            id=f"note:{md_file.stem}",
            label=title,
            node_type=NodeType.DOCUMENT,
            metadata={
                "source": "obsidian",
                "file": file_key,
                "tags": tags,
                "wikilinks": wikilinks,
            },
        )
        try:
            graph_svc.add_node(note_node)
            graph_nodes += 1
        except Exception:
            pass

        # Create edges from wikilinks
        for link in wikilinks:
            target_id = f"note:{link}"
            # Ensure target node exists (may be unprocessed)
            try:
                graph_svc.add_node(GraphNode(
                    id=target_id,
                    label=link,
                    node_type=NodeType.DOCUMENT,
                    metadata={"source": "obsidian", "pending": True},
                ))
            except Exception:
                pass
            try:
                graph_svc.add_edge(GraphEdge(
                    source=f"note:{md_file.stem}",
                    target=target_id,
                    edge_type=EdgeType.MENTIONS,
                ))
                graph_edges += 1
            except Exception:
                pass

        # Update sync state
        synced[file_key] = {"mtime": mtime, "doc_id": doc.id}

    state["synced_files"] = synced
    _save_sync_state(state)

    return {
        "imported": imported,
        "skipped": skipped,
        "graph_nodes_added": graph_nodes,
        "graph_edges_added": graph_edges,
        "total_files": len(md_files),
    }


def get_sync_status() -> dict:
    """Get current sync state."""
    state = _load_sync_state()
    return {
        "last_sync": state.get("last_sync"),
        "files_synced": len(state.get("synced_files", {})),
    }


def clear_sync_state():
    """Reset sync state (will re-import everything on next sync)."""
    _save_sync_state({"synced_files": {}, "last_sync": None})
