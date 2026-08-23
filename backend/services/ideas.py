"""Идеи — отдельно от задач (services/tasks.py).

Задача — то, что делается сейчас. Идея — то, что откладывается на будущую
разработку: фаундер сказал «запиши это на будущее», либо система (я сам,
позже — агенты) заметила что-то стоящее по ходу работы и предложила сама.
Спецификация — фаундер, 23.08.2026 (см. память nexus-os-ideas-panel).

locked_update сразу, без промежуточного unlocked-варианта — тот же класс
гонки (веб-чат и Telegram разные процессы), что уже нашёлся и починен в
memory.py/curator.py, повторять его здесь незачем.
"""
import uuid
from datetime import datetime

from ..core.config import IDEAS_FILE, ensure_data_dir
from ..core.errors import NotFoundError
from ..core.jsonio import locked_update, read_json
from ..models.schemas import Idea, IdeaCreate, IdeaSource, IdeaUpdate


def _load() -> list[dict]:
    ensure_data_dir()
    return read_json(IDEAS_FILE, [])


def list_ideas(status: str | None = None) -> list[Idea]:
    ideas = [Idea(**i) for i in _load()]
    if status:
        ideas = [i for i in ideas if i.status.value == status]
    return sorted(ideas, key=lambda i: i.created_at, reverse=True)


def get_idea(idea_id: str) -> Idea:
    for i in _load():
        if i["id"] == idea_id:
            return Idea(**i)
    raise NotFoundError("Idea", idea_id)


def create_idea(data: IdeaCreate) -> Idea:
    idea = Idea(
        id=str(uuid.uuid4())[:8],
        content=data.content,
        source=data.source,
        context=data.context,
    )
    ensure_data_dir()
    locked_update(IDEAS_FILE, lambda ideas: ideas + [idea.model_dump()], default=[])
    return idea


def update_idea(idea_id: str, data: IdeaUpdate) -> Idea:
    updated: dict | None = None

    def mutate(ideas: list[dict]) -> list[dict]:
        nonlocal updated
        for i, idea in enumerate(ideas):
            if idea["id"] != idea_id:
                continue
            if data.content is not None:
                idea["content"] = data.content
            if data.status is not None:
                idea["status"] = data.status.value
            idea["updated_at"] = datetime.utcnow().isoformat()
            ideas[i] = idea
            updated = idea
            break
        return ideas

    ensure_data_dir()
    locked_update(IDEAS_FILE, mutate, default=[])
    if updated is None:
        raise NotFoundError("Idea", idea_id)
    return Idea(**updated)


def delete_idea(idea_id: str) -> bool:
    found = False

    def mutate(ideas: list[dict]) -> list[dict]:
        nonlocal found
        remaining = [i for i in ideas if i["id"] != idea_id]
        found = len(remaining) != len(ideas)
        return remaining

    ensure_data_dir()
    locked_update(IDEAS_FILE, mutate, default=[])
    if not found:
        raise NotFoundError("Idea", idea_id)
    return True


def propose(content: str, context: str = "") -> Idea:
    """Система сама предлагает идею — источник SYSTEM, не FOUNDER. Тот же
    список, помеченный иначе: на экране фаундер видит, кто это предложил."""
    return create_idea(IdeaCreate(content=content, source=IdeaSource.SYSTEM, context=context))
