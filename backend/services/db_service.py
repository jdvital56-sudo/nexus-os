"""Database service layer for CRUD operations."""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func
from typing import Optional, List
from datetime import datetime

from ..database.models import (
    Document as DocumentModel,
    Task as TaskModel,
    GraphNode as GraphNodeModel,
    GraphEdge as GraphEdgeModel,
    Agent as AgentModel,
    Memory as MemoryModel,
    Skill as SkillModel,
)
from ..models.schemas import (
    DocumentCreate, DocumentUpdate,
    TaskCreate, TaskUpdate,
    GraphNode, GraphEdge,
    AgentCreate, AgentUpdate,
)


# === Document Operations ===

def get_documents(db: Session, limit: int = 100, offset: int = 0) -> List[DocumentModel]:
    """Get all documents with pagination."""
    return db.query(DocumentModel).offset(offset).limit(limit).all()


def get_document(db: Session, doc_id: str) -> Optional[DocumentModel]:
    """Get a single document by ID."""
    return db.query(DocumentModel).filter(DocumentModel.id == doc_id).first()


def create_document(db: Session, doc: DocumentCreate) -> DocumentModel:
    """Create a new document."""
    from uuid import uuid4
    db_doc = DocumentModel(
        id=str(uuid4()),
        title=doc.title,
        content=doc.content,
        doc_type=doc.doc_type,
        tags=doc.tags,
        source=doc.source,
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc


def update_document(db: Session, doc_id: str, update: DocumentUpdate) -> Optional[DocumentModel]:
    """Update an existing document."""
    db_doc = get_document(db, doc_id)
    if not db_doc:
        return None
    
    if update.title is not None:
        db_doc.title = update.title
    if update.content is not None:
        db_doc.content = update.content
    if update.tags is not None:
        db_doc.tags = update.tags
    
    db_doc.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_doc)
    return db_doc


def delete_document(db: Session, doc_id: str) -> bool:
    """Delete a document."""
    db_doc = get_document(db, doc_id)
    if not db_doc:
        return False
    
    db.delete(db_doc)
    db.commit()
    return True


# === Task Operations ===

def get_tasks(db: Session, status: str = None, limit: int = 100) -> List[TaskModel]:
    """Get tasks with optional status filter."""
    query = db.query(TaskModel)
    if status:
        query = query.filter(TaskModel.status == status)
    return query.limit(limit).all()


def get_task(db: Session, task_id: str) -> Optional[TaskModel]:
    """Get a single task by ID."""
    return db.query(TaskModel).filter(TaskModel.id == task_id).first()


def create_task(db: Session, task: TaskCreate) -> TaskModel:
    """Create a new task."""
    from uuid import uuid4
    db_task = TaskModel(
        id=str(uuid4()),
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        assigned_agent=task.assigned_agent,
        tags=task.tags,
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def update_task(db: Session, task_id: str, update: TaskUpdate) -> Optional[TaskModel]:
    """Update an existing task."""
    db_task = get_task(db, task_id)
    if not db_task:
        return None
    
    if update.title is not None:
        db_task.title = update.title
    if update.description is not None:
        db_task.description = update.description
    if update.status is not None:
        db_task.status = update.status
    if update.priority is not None:
        db_task.priority = update.priority
    if update.assigned_agent is not None:
        db_task.assigned_agent = update.assigned_agent
    
    db_task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_task)
    return db_task


def delete_task(db: Session, task_id: str) -> bool:
    """Delete a task."""
    db_task = get_task(db, task_id)
    if not db_task:
        return False
    
    db.delete(db_task)
    db.commit()
    return True


# === Graph Node Operations ===

def get_graph_nodes(db: Session, node_type: str = None, limit: int = 100) -> List[GraphNodeModel]:
    """Get graph nodes with optional type filter."""
    query = db.query(GraphNodeModel)
    if node_type:
        query = query.filter(GraphNodeModel.node_type == node_type)
    return query.limit(limit).all()


def get_graph_node(db: Session, node_id: str) -> Optional[GraphNodeModel]:
    """Get a single graph node by ID."""
    return db.query(GraphNodeModel).filter(GraphNodeModel.id == node_id).first()


def create_graph_node(db: Session, node: GraphNode) -> GraphNodeModel:
    """Create a new graph node."""
    db_node = GraphNodeModel(
        id=node.id,
        label=node.label,
        node_type=node.node_type,
        node_metadata=node.model_dump().get('metadata', {}),
    )
    db.add(db_node)
    db.commit()
    db.refresh(db_node)
    return db_node


def delete_graph_node(db: Session, node_id: str) -> bool:
    """Delete a graph node."""
    db_node = get_graph_node(db, node_id)
    if not db_node:
        return False
    
    db.delete(db_node)
    db.commit()
    return True


# === Graph Edge Operations ===

def get_graph_edges(db: Session, source: str = None, target: str = None) -> List[GraphEdgeModel]:
    """Get graph edges with optional filters."""
    query = db.query(GraphEdgeModel)
    if source:
        query = query.filter(GraphEdgeModel.source == source)
    if target:
        query = query.filter(GraphEdgeModel.target == target)
    return query.all()


def create_graph_edge(db: Session, edge: GraphEdge) -> GraphEdgeModel:
    """Create a new graph edge."""
    from uuid import uuid4
    db_edge = GraphEdgeModel(
        id=str(uuid4()),
        source=edge.source,
        target=edge.target,
        edge_type=edge.edge_type,
        weight=edge.weight,
        edge_metadata=edge.model_dump().get('metadata', {}),
    )
    db.add(db_edge)
    db.commit()
    db.refresh(db_edge)
    return db_edge


def delete_graph_edge(db: Session, edge_id: str) -> bool:
    """Delete a graph edge."""
    db_edge = db.query(GraphEdgeModel).filter(GraphEdgeModel.id == edge_id).first()
    if not db_edge:
        return False
    
    db.delete(db_edge)
    db.commit()
    return True


# === Agent Operations ===

def get_agents(db: Session, status: str = None) -> List[AgentModel]:
    """Get agents with optional status filter."""
    query = db.query(AgentModel)
    if status:
        query = query.filter(AgentModel.status == status)
    return query.all()


def get_agent(db: Session, agent_id: str) -> Optional[AgentModel]:
    """Get a single agent by ID."""
    return db.query(AgentModel).filter(AgentModel.id == agent_id).first()


def create_agent(db: Session, agent: AgentCreate) -> AgentModel:
    """Create a new agent."""
    from uuid import uuid4
    db_agent = AgentModel(
        id=str(uuid4()),
        name=agent.name,
        role=agent.role,
        description=agent.description,
        model=agent.model,
        config=agent.config,
    )
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)
    return db_agent


def update_agent(db: Session, agent_id: str, update: AgentUpdate) -> Optional[AgentModel]:
    """Update an existing agent."""
    db_agent = get_agent(db, agent_id)
    if not db_agent:
        return None
    
    if update.name is not None:
        db_agent.name = update.name
    if update.description is not None:
        db_agent.description = update.description
    if update.model is not None:
        db_agent.model = update.model
    if update.config is not None:
        db_agent.config = update.config
    if update.status is not None:
        db_agent.status = update.status
        if update.status.value == "running":
            db_agent.last_run = datetime.utcnow()
    
    db.commit()
    db.refresh(db_agent)
    return db_agent


def delete_agent(db: Session, agent_id: str) -> bool:
    """Delete an agent."""
    db_agent = get_agent(db, agent_id)
    if not db_agent:
        return False
    
    db.delete(db_agent)
    db.commit()
    return True


# === Memory Operations ===

def get_memories(db: Session, session_id: str = None, limit: int = 50) -> List[MemoryModel]:
    """Get memories with optional session filter."""
    query = db.query(MemoryModel)
    if session_id:
        query = query.filter(MemoryModel.session_id == session_id)
    return query.order_by(MemoryModel.created_at.desc()).limit(limit).all()


def create_memory(db: Session, session_id: str, content: str, memory_type: str = "conversation") -> MemoryModel:
    """Create a new memory."""
    from uuid import uuid4
    db_memory = MemoryModel(
        id=str(uuid4()),
        session_id=session_id,
        content=content,
        memory_type=memory_type,
    )
    db.add(db_memory)
    db.commit()
    db.refresh(db_memory)
    return db_memory


def delete_memory(db: Session, memory_id: str) -> bool:
    """Delete a memory."""
    db_memory = db.query(MemoryModel).filter(MemoryModel.id == memory_id).first()
    if not db_memory:
        return False
    
    db.delete(db_memory)
    db.commit()
    return True


# === Skill Operations ===

def get_skills(db: Session) -> List[SkillModel]:
    """Get all skills."""
    return db.query(SkillModel).all()


def get_skill(db: Session, skill_id: str) -> Optional[SkillModel]:
    """Get a single skill by ID."""
    return db.query(SkillModel).filter(SkillModel.id == skill_id).first()


def create_skill(db: Session, skill_id: str, name: str, description: str, category: str, contract: dict) -> SkillModel:
    """Create or update a skill."""
    existing = get_skill(db, skill_id)
    if existing:
        existing.name = name
        existing.description = description
        existing.category = category
        existing.contract = contract
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing
    
    db_skill = SkillModel(
        id=skill_id,
        name=name,
        description=description,
        category=category,
        contract=contract,
    )
    db.add(db_skill)
    db.commit()
    db.refresh(db_skill)
    return db_skill


def delete_skill(db: Session, skill_id: str) -> bool:
    """Delete a skill."""
    db_skill = get_skill(db, skill_id)
    if not db_skill:
        return False
    
    db.delete(db_skill)
    db.commit()
    return True
