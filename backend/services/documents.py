"""Document service — CRUD + import + graph linking."""
import json
import uuid
from pathlib import Path
from ..core.config import DOCUMENTS_FILE, ensure_data_dir
from ..core.errors import NotFoundError
from ..models.schemas import Document, DocumentCreate, DocumentUpdate, DocType
from .tagger import generate_tags, create_document_graph_nodes, create_concept_node, find_related_documents
from . import graph as graph_svc
from ..core.jsonio import read_json, write_json


def _load() -> list[dict]:
    ensure_data_dir()
    if DOCUMENTS_FILE.exists():
        return read_json(DOCUMENTS_FILE, [])
    return []


def _save(docs: list[dict]):
    ensure_data_dir()
    write_json(DOCUMENTS_FILE, docs)


def list_documents(tag: str | None = None, doc_type: str | None = None) -> list[Document]:
    docs = [Document(**d) for d in _load()]
    if tag:
        docs = [d for d in docs if tag in d.tags]
    if doc_type:
        docs = [d for d in docs if d.doc_type.value == doc_type]
    return docs


def get_document(doc_id: str) -> Document:
    docs = _load()
    for d in docs:
        if d["id"] == doc_id:
            return Document(**d)
    raise NotFoundError("Document", doc_id)


def create_document(data: DocumentCreate, auto_tag: bool = True) -> Document:
    docs = _load()
    
    # Auto-generate tags if not provided
    tags = list(data.tags)
    if auto_tag and not tags:
        tags = generate_tags(data.content, data.title)
    
    doc = Document(
        id=str(uuid.uuid4())[:8],
        title=data.title,
        content=data.content,
        doc_type=data.doc_type,
        tags=tags,
        source=data.source,
    )
    docs.append(doc.model_dump())
    _save(docs)
    
    # Link to knowledge graph
    _link_to_graph(doc, docs)
    
    return doc


def _link_to_graph(doc: Document, all_docs: list[dict]):
    """Create graph nodes and edges for a document."""
    try:
        # 1. Create document node
        doc_node, tag_edges = create_document_graph_nodes(doc.id, doc.title, doc.tags)
        graph_svc.add_node(doc_node)
        
        # 2. Create concept nodes for tags and link
        for tag in doc.tags:
            concept = create_concept_node(tag)
            try:
                graph_svc.add_node(concept)
            except Exception:
                pass  # concept already exists, skip
        
        # 3. Add edges from document to concepts
        for edge in tag_edges:
            try:
                graph_svc.add_edge(edge)
            except Exception:
                pass  # edge already exists or node missing
        
        # 4. Find and link related documents
        related_edges = find_related_documents(doc.id, doc.tags, all_docs)
        for edge in related_edges:
            try:
                graph_svc.add_edge(edge)
            except Exception:
                pass
    except Exception:
        pass  # graph linking is best-effort, don't fail document creation


def update_document(doc_id: str, data: DocumentUpdate) -> Document:
    docs = _load()
    for i, d in enumerate(docs):
        if d["id"] == doc_id:
            if data.title is not None:
                d["title"] = data.title
            if data.content is not None:
                d["content"] = data.content
            if data.tags is not None:
                d["tags"] = data.tags
            from datetime import datetime
            d["updated_at"] = datetime.utcnow().isoformat()
            docs[i] = d
            _save(docs)
            return Document(**d)
    raise NotFoundError("Document", doc_id)


def delete_document(doc_id: str) -> bool:
    docs = _load()
    new_docs = [d for d in docs if d["id"] != doc_id]
    if len(new_docs) == len(docs):
        raise NotFoundError("Document", doc_id)
    _save(new_docs)
    return True


def import_markdown_dir(dir_path: str) -> list[Document]:
    """Import all .md files from a directory with auto-tagging."""
    p = Path(dir_path)
    if not p.is_dir():
        raise NotFoundError("Directory", dir_path)
    created = []
    for md_file in sorted(p.glob("**/*.md")):
        content = md_file.read_text(encoding="utf-8", errors="replace")
        title = md_file.stem.replace("-", " ").replace("_", " ").title()
        doc = create_document(DocumentCreate(
            title=title,
            content=content,
            doc_type=DocType.MARKDOWN,
            source=str(md_file),
        ), auto_tag=True)
        created.append(doc)
    return created
