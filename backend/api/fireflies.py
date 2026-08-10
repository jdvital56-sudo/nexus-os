"""Fireflies API routes — call transcript ingestion."""
from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel
from typing import Any
from ..services import fireflies as svc
from ..core.auth import get_token_dep

router = APIRouter(prefix="/api/fireflies", tags=["fireflies"])
auth = get_token_dep()


class TranscriptRequest(BaseModel):
    text: str
    title: str = ""
    participants: list[str] = []
    auto_memory: bool = True


@router.post("/transcript")
def ingest_transcript(req: TranscriptRequest, _=Depends(auth)):
    """Ingest a call transcript — parse, tag, create memory, link graph."""
    return svc.ingest_transcript(
        text=req.text,
        title=req.title,
        participants=req.participants,
        auto_memory=req.auto_memory,
    )


@router.post("/parse")
def parse_transcript(req: TranscriptRequest, _=Depends(auth)):
    """Parse a transcript without ingesting (dry run)."""
    return svc.parse_transcript(req.text)


@router.get("/history")
def call_history(person: str | None = None, limit: int = 20, _=Depends(auth)):
    return svc.get_call_history(person=person, limit=limit)
