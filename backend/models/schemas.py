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
