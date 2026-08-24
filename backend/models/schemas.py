"""Pydantic schemas for all NEXSYS resources."""
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime
from enum import Enum


# === Documents ===

class DocType(str, Enum):
    MARKDOWN = "markdown"
    TEXT = "text"
    CSV = "csv"
    JSON = "json"
    OTHER = "other"


class DocumentCreate(BaseModel):
    title: str
    content: str
    doc_type: DocType = DocType.MARKDOWN
    tags: list[str] = Field(default_factory=list)
    source: str | None = None


class Document(BaseModel):
    id: str
    title: str
    content: str
    doc_type: DocType
    tags: list[str] = Field(default_factory=list)
    source: str | None = None
    graph_node_id: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class DocumentUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None


# === Tasks ===

class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_agent: str | None = None
    tags: list[str] = Field(default_factory=list)


class Task(BaseModel):
    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_agent: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assigned_agent: str | None = None


# === Идеи ===
# Отдельно от задач (Task) — задача делается сейчас, идея откладывается на
# будущую разработку. Спецификация от фаундера 23.08.2026: попадает сюда
# либо по его прямой просьбе («запиши это на будущее»), либо по моей
# собственной инициативе, когда я замечаю что-то стоящее по ходу работы.

class IdeaSource(str, Enum):
    FOUNDER = "founder"
    SYSTEM = "system"


class IdeaStatus(str, Enum):
    NEW = "new"
    CONSIDERED = "considered"
    PLANNED = "planned"
    DISMISSED = "dismissed"


class Idea(BaseModel):
    id: str
    content: str
    source: IdeaSource = IdeaSource.FOUNDER
    status: IdeaStatus = IdeaStatus.NEW
    context: str = ""
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class IdeaCreate(BaseModel):
    content: str
    source: IdeaSource = IdeaSource.FOUNDER
    context: str = ""


class IdeaUpdate(BaseModel):
    content: str | None = None
    status: IdeaStatus | None = None


# === Content Factory ===
# Идея -> сценарий (LLM) -> озвучка/картинка/видео (fal.ai) -> approve/reject
# человеком. Автопубликация не входит — см. шапку services/content_factory.py.

class ContentStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"  # ушло кнопками в Telegram, ждём ответа
    APPROVED = "approved"
    SCHEDULED = "scheduled"  # одобрено и стоит на дату, ждёт напоминания
    POSTED = "posted"  # фаундер отметил вручную, что опубликовал
    REJECTED = "rejected"


class ContentPlanRequest(BaseModel):
    topic: str
    count: int = 3
    platforms: list[str] = Field(default_factory=lambda: ["tiktok", "instagram"])
    scheduled_at: str | None = None


class ContentItem(BaseModel):
    id: str
    topic: str
    script: str
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    status: ContentStatus = ContentStatus.DRAFT
    # Одно общее время на все площадки черновика: разное время под разные
    # площадки — это по сути разные черновики (решение фаундера 23.08.2026).
    scheduled_at: str | None = None
    # Когда ушло напоминание «пора постить». Хранится, а не держится в
    # памяти процесса: иначе перезапуск бэкенда присылает напоминание заново.
    reminded_at: str | None = None
    voice_file: str | None = None
    image_file: str | None = None
    video_file: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# === Knowledge Graph ===

class NodeType(str, Enum):
    DOCUMENT = "document"
    TASK = "task"
    MEMORY = "memory"
    CONCEPT = "concept"
    AGENT = "agent"
    DECISION = "decision"
    SESSION = "session"
    FILE = "file"


class EdgeType(str, Enum):
    RELATED = "related"
    DEPENDS_ON = "depends_on"
    CREATED_BY = "created_by"
    MENTIONS = "mentions"
    CONTAINS = "contains"
    LEADS_TO = "leads_to"


class GraphNode(BaseModel):
    id: str
    label: str
    node_type: NodeType
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class GraphEdge(BaseModel):
    source: str
    target: str
    edge_type: EdgeType = EdgeType.RELATED
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphStats(BaseModel):
    nodes: int
    edges: int
    node_types: dict[str, int]
    connected_components: int


class GraphQuery(BaseModel):
    node_type: NodeType | None = None
    label_contains: str | None = None
    limit: int = 50


# === Agents ===

class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    PAUSED = "paused"


class AgentRole(str, Enum):
    BUILDER = "builder"
    LIBRARIAN = "librarian"
    REVIEWER = "reviewer"
    RESEARCHER = "researcher"
    MONITOR = "monitor"
    CURATOR = "curator"
    JARVIS = "jarvis"


class AgentCreate(BaseModel):
    name: str
    role: AgentRole
    description: str = ""
    model: str = "default"
    config: dict[str, Any] = Field(default_factory=dict)


class Agent(BaseModel):
    id: str
    name: str
    role: AgentRole
    description: str = ""
    status: AgentStatus = AgentStatus.IDLE
    model: str = "default"
    config: dict[str, Any] = Field(default_factory=dict)
    last_run: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    model: str | None = None
    config: dict[str, Any] | None = None
    status: AgentStatus | None = None


class AgentRunRequest(BaseModel):
    task: str
    context: dict[str, Any] = Field(default_factory=dict)


class AgentRunResult(BaseModel):
    agent_id: str
    status: str
    output: str
    duration_ms: int
    tokens_used: int | None = None


# === Библиотека источников ===


class SourceKind(str, Enum):
    SITE = "site"
    RSS = "rss"
    BLOG = "blog"
    DOCS = "docs"
    SOCIAL = "social"


class SourceStatus(str, Enum):
    NEVER = "never"
    OK = "ok"
    ERROR = "error"


class SourceCreate(BaseModel):
    url: str
    title: str = ""
    kind: SourceKind = SourceKind.SITE
    topics: list[str] = Field(default_factory=list)
    # Доверие 0..1. Половина по умолчанию: содержимое чужого сайта — это
    # данные, а не указания системе, и повышать доверие можно только вручную.
    trust: float = 0.5
    check_interval_hours: int = 24
    enabled: bool = True
    notes: str = ""


class Source(BaseModel):
    id: str
    url: str
    title: str = ""
    kind: SourceKind = SourceKind.SITE
    topics: list[str] = Field(default_factory=list)
    trust: float = 0.5
    check_interval_hours: int = 24
    enabled: bool = True
    notes: str = ""
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    last_checked_at: str | None = None
    last_status: SourceStatus = SourceStatus.NEVER
    last_error: str = ""
    check_count: int = 0
    error_streak: int = 0
    items_found: int = 0


class SourceUpdate(BaseModel):
    url: str | None = None
    title: str | None = None
    kind: SourceKind | None = None
    topics: list[str] | None = None
    trust: float | None = None
    check_interval_hours: int | None = None
    enabled: bool | None = None
    notes: str | None = None
