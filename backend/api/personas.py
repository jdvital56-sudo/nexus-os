"""Personas API routes — Пантеон и системный промпт Hermes.

Бэкенд для Mission Control (PR-22): правки отсюда влияют на следующее
сообщение в любом канале и переживают рестарт.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.auth import get_token_dep
from ..services import personas as svc

router = APIRouter(prefix="/api/personas", tags=["personas"])
auth = get_token_dep()


class PersonaCreate(BaseModel):
    name: str
    description: str
    model: str
    provider: str
    system_prompt: str


class PersonaUpdate(BaseModel):
    description: str | None = None
    model: str | None = None
    provider: str | None = None
    system_prompt: str | None = None


class SystemPromptUpdate(BaseModel):
    system_prompt: str


# Статические пути объявлены до /{name}, иначе FastAPI примет их за имя персоны
@router.get("/system-prompt")
def get_system_prompt(_=Depends(auth)):
    return {"system_prompt": svc.get_system_prompt()}


@router.put("/system-prompt")
def set_system_prompt(req: SystemPromptUpdate, _=Depends(auth)):
    try:
        return {"system_prompt": svc.set_system_prompt(req.system_prompt)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class CharacterUpdate(BaseModel):
    humor: int | None = None
    warmth: int | None = None
    verbosity: int | None = None
    address: str | None = None
    language: str | None = None


@router.get("/character")
def get_character(_=Depends(auth)):
    """Характер Hermes: ползунки и то, во что они разворачиваются для модели."""
    character = svc.get_character()
    return {**character, "prompt": svc.describe_character(character)}


@router.put("/character")
def set_character(req: CharacterUpdate, _=Depends(auth)):
    character = svc.set_character(req.model_dump(exclude_unset=True))
    return {**character, "prompt": svc.describe_character(character)}


@router.post("/reset")
def reset(_=Depends(auth)):
    return svc.reset_to_defaults()


@router.get("")
def list_personas(_=Depends(auth)):
    return svc.list_personas()


@router.post("", status_code=201)
def create_persona(req: PersonaCreate, _=Depends(auth)):
    try:
        return svc.create_persona(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{name}")
def get_persona(name: str, _=Depends(auth)):
    persona = svc.get_persona(name)
    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona '{name}' not found")
    return persona


@router.put("/{name}")
def update_persona(name: str, req: PersonaUpdate, _=Depends(auth)):
    return svc.update_persona(name, req.model_dump(exclude_unset=True))


@router.delete("/{name}")
def delete_persona(name: str, _=Depends(auth)):
    try:
        svc.delete_persona(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}
