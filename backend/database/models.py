"""SQLAlchemy ORM models for NEXSYS."""
from sqlalchemy import Column, String, Text, DateTime, Enum, Integer, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import enum

Base = declarative_base()


# === Enums ===

class DocType(str, enum.Enum):
    MARKDOWN = "markdown"
    TEXT = "text"
    CSV = "csv"
    JSON = "json"
    OTHER = "other"


class TaskStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NodeType(str, enum.Enum):
    DOCUMENT = "document"
    TASK = "task"
    MEMORY = "memory"
    CONCEPT = "concept"
    AGENT = "agent"
    DECISION = "decision"
    SESSION = "session"
    FILE = "file"


class EdgeType(str, enum.Enum):
    RELATED = "related"
    DEPENDS_ON = "depends_on"
    CREATED_BY = "created_by"
    MENTIONS = "mentions"
    CONTAINS = "contains"
    LEADS_TO = "leads_to"


class AgentStatus(str, enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    PAUSED = "paused"


class AgentRole(str, enum.Enum):
    BUILDER = "builder"
    LIBRARIAN = "librarian"
    REVIEWER = "reviewer"
    RESEARCHER = "researcher"
    MONITOR = "monitor"
    JARVIS = "jarvis"


# === Models ===

class Document(Base):
    """Document model for storing content."""
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False)
    doc_type = Column(Enum(DocType), default=DocType.MARKDOWN)
    tags = Column(JSON, default=list)
    source = Column(String, nullable=True)
    graph_node_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Task(Base):
    """Task model for task management."""
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    description = Column(Text, default="")
    status = Column(Enum(TaskStatus), default=TaskStatus.TODO)
    priority = Column(Enum(TaskPriority), default=TaskPriority.MEDIUM)
    assigned_agent = Column(String, nullable=True, index=True)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GraphNode(Base):
    """Knowledge graph node model."""
    __tablename__ = "graph_nodes"

    id = Column(String, primary_key=True, index=True)
    label = Column(String, nullable=False, index=True)
    node_type = Column(Enum(NodeType), nullable=False)
    node_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    outgoing_edges = relationship("GraphEdge", foreign_keys="GraphEdge.source", back_populates="source_node", cascade="all, delete-orphan")
    incoming_edges = relationship("GraphEdge", foreign_keys="GraphEdge.target", back_populates="target_node")


class GraphEdge(Base):
    """Knowledge graph edge model."""
    __tablename__ = "graph_edges"

    id = Column(String, primary_key=True, index=True)
    source = Column(String, ForeignKey("graph_nodes.id"), nullable=False, index=True)
    target = Column(String, ForeignKey("graph_nodes.id"), nullable=False, index=True)
    edge_type = Column(Enum(EdgeType), default=EdgeType.RELATED)
    weight = Column(Float, default=1.0)
    edge_metadata = Column(JSON, default=dict)

    # Relationships
    source_node = relationship("GraphNode", foreign_keys=[source], back_populates="outgoing_edges")
    target_node = relationship("GraphNode", foreign_keys=[target], back_populates="incoming_edges")


class Agent(Base):
    """Agent model for autonomous agents."""
    __tablename__ = "agents"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    role = Column(Enum(AgentRole), nullable=False)
    description = Column(Text, default="")
    status = Column(Enum(AgentStatus), default=AgentStatus.IDLE)
    model = Column(String, default="default")
    config = Column(JSON, default=dict)
    last_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Memory(Base):
    """Memory model for conversation and context storage."""
    __tablename__ = "memories"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False)
    memory_type = Column(String, default="conversation")  # conversation, decision, context
    importance = Column(Float, default=1.0)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class Skill(Base):
    """Skill model for storing skill definitions."""
    __tablename__ = "skills"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    category = Column(String, default="general")
    contract = Column(JSON, nullable=False)  # The skill JSON contract
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
