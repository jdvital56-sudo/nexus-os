"""Tests for database service layer."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database.connection import Base, get_db
from backend.database.models import Document as DocumentModel
from backend.models.schemas import DocumentCreate, DocType
from backend.services.db_service import (
    create_document,
    get_document,
    get_documents,
    update_document,
    delete_document,
)


# Test database setup
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_create_document(db_session):
    """Test document creation."""
    doc_data = DocumentCreate(
        title="Test Document",
        content="This is test content",
        doc_type=DocType.MARKDOWN,
        tags=["test", "sample"],
    )
    
    doc = create_document(db_session, doc_data)
    
    assert doc.id is not None
    assert doc.title == "Test Document"
    assert doc.content == "This is test content"
    assert doc.doc_type == DocType.MARKDOWN
    assert "test" in doc.tags


def test_get_document(db_session):
    """Test retrieving a document by ID."""
    doc_data = DocumentCreate(
        title="Get Test",
        content="Content to retrieve",
    )
    
    created = create_document(db_session, doc_data)
    retrieved = get_document(db_session, created.id)
    
    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.title == "Get Test"


def test_get_documents(db_session):
    """Test getting all documents."""
    for i in range(3):
        doc_data = DocumentCreate(
            title=f"Document {i}",
            content=f"Content {i}",
        )
        create_document(db_session, doc_data)
    
    docs = get_documents(db_session)
    assert len(docs) == 3


def test_update_document(db_session):
    """Test updating a document."""
    from backend.models.schemas import DocumentUpdate
    
    doc_data = DocumentCreate(
        title="Original Title",
        content="Original Content",
    )
    
    created = create_document(db_session, doc_data)
    update_data = DocumentUpdate(title="Updated Title")
    
    updated = update_document(db_session, created.id, update_data)
    
    assert updated is not None
    assert updated.title == "Updated Title"
    assert updated.content == "Original Content"


def test_delete_document(db_session):
    """Test deleting a document."""
    doc_data = DocumentCreate(
        title="To Delete",
        content="Will be deleted",
    )
    
    created = create_document(db_session, doc_data)
    deleted = delete_document(db_session, created.id)
    
    assert deleted is True
    assert get_document(db_session, created.id) is None


def test_delete_nonexistent_document(db_session):
    """Test deleting a document that doesn't exist."""
    deleted = delete_document(db_session, "nonexistent-id")
    assert deleted is False
