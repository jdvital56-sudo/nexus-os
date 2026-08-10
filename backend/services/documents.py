"""Document service — CRUD + import + graph linking."""
import json
import uuid
from pathlib import Path
from ..core.config import DOCUMENTS_FILE, ensure_data_dir
from ..core.errors import NotFoundError
from ..models.schemas import Document, DocumentCreate, DocumentUpdate, DocType


def _load() -> list[dict]:
    ensure_data_dir()
    if DOCUMENTS_FILE.exists():
        return json.loads(DOCUMENTS_FILE.read_text())
    return []


def _save(docs: list[dict]):
    ensure_data_dir()
    DOCUMENTS_FILE.write_text(json.dumps(docs, indent=2, ensure_ascii=False))


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


def create_document(data: DocumentCreate) -> Document:
    docs = _load()
    doc = Document(
        id=str(uuid.uuid4())[:8],
        title=data.title,
        content=data.content,
        doc_type=data.doc_type,
        tags=data.tags,
        source=data.source,
    )
    docs.append(doc.model_dump())
    _save(docs)
    return doc


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
    """Import all .md files from a directory."""
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
        ))
        created.append(doc)
    return created
