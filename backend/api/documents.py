"""Document API routes."""
from fastapi import APIRouter, Query, Depends
from ..models.schemas import Document, DocumentCreate, DocumentUpdate
from ..services import documents as svc
from ..core.auth import get_token_dep

router = APIRouter(prefix="/api/documents", tags=["documents"])
auth = get_token_dep()


@router.get("", response_model=list[Document])
def list_docs(tag: str | None = None, doc_type: str | None = None, _=Depends(auth)):
    return svc.list_documents(tag=tag, doc_type=doc_type)


@router.get("/{doc_id}", response_model=Document)
def get_doc(doc_id: str, _=Depends(auth)):
    return svc.get_document(doc_id)


@router.post("", response_model=Document, status_code=201)
def create_doc(data: DocumentCreate, _=Depends(auth)):
    return svc.create_document(data)


@router.patch("/{doc_id}", response_model=Document)
def update_doc(doc_id: str, data: DocumentUpdate, _=Depends(auth)):
    return svc.update_document(doc_id, data)


@router.delete("/{doc_id}")
def delete_doc(doc_id: str, _=Depends(auth)):
    svc.delete_document(doc_id)
    return {"ok": True}


@router.post("/import/markdown", response_model=list[Document])
def import_markdown(dir_path: str = Query(..., description="Directory with .md files"), _=Depends(auth)):
    return svc.import_markdown_dir(dir_path)
