"""Task service — CRUD."""
import json
import uuid
from ..core.config import TASKS_FILE, ensure_data_dir
from ..core.errors import NotFoundError
from ..models.schemas import Task, TaskCreate, TaskUpdate, TaskStatus


def _load() -> list[dict]:
    ensure_data_dir()
    if TASKS_FILE.exists():
        return json.loads(TASKS_FILE.read_text())
    return []


def _save(tasks: list[dict]):
    ensure_data_dir()
    TASKS_FILE.write_text(json.dumps(tasks, indent=2, ensure_ascii=False))


def list_tasks(status: str | None = None, assigned_agent: str | None = None) -> list[Task]:
    tasks = [Task(**t) for t in _load()]
    if status:
        tasks = [t for t in tasks if t.status.value == status]
    if assigned_agent:
        tasks = [t for t in tasks if t.assigned_agent == assigned_agent]
    return tasks


def get_task(task_id: str) -> Task:
    tasks = _load()
    for t in tasks:
        if t["id"] == task_id:
            return Task(**t)
    raise NotFoundError("Task", task_id)


def create_task(data: TaskCreate) -> Task:
    tasks = _load()
    task = Task(
        id=str(uuid.uuid4())[:8],
        title=data.title,
        description=data.description,
        status=data.status,
        priority=data.priority,
        assigned_agent=data.assigned_agent,
        tags=data.tags,
    )
    tasks.append(task.model_dump())
    _save(tasks)
    return task


def update_task(task_id: str, data: TaskUpdate) -> Task:
    tasks = _load()
    for i, t in enumerate(tasks):
        if t["id"] == task_id:
            if data.title is not None:
                t["title"] = data.title
            if data.description is not None:
                t["description"] = data.description
            if data.status is not None:
                t["status"] = data.status.value
            if data.priority is not None:
                t["priority"] = data.priority.value
            if data.assigned_agent is not None:
                t["assigned_agent"] = data.assigned_agent
            from datetime import datetime
            t["updated_at"] = datetime.utcnow().isoformat()
            tasks[i] = t
            _save(tasks)
            return Task(**t)
    raise NotFoundError("Task", task_id)


def delete_task(task_id: str) -> bool:
    tasks = _load()
    new_tasks = [t for t in tasks if t["id"] != task_id]
    if len(new_tasks) == len(tasks):
        raise NotFoundError("Task", task_id)
    _save(new_tasks)
    return True
