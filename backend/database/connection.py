"""Database connection and session management."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from pathlib import Path
import os

# Get DATA_DIR from environment or use default
DATA_DIR = Path(os.getenv("NEXSYS_DATA_DIR", Path.home() / ".nexsys"))

# Database URL - using SQLite by default
DATABASE_URL = f"sqlite:///{DATA_DIR}/nexsys.db"

# Create engine with SQLite-specific settings
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite
    echo=False,  # Set to True for SQL debugging
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Dependency for getting database session in FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database - create tables."""
    from .models import Base
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


def reset_db():
    """Reset database - drop all tables."""
    from .models import Base
    Base.metadata.drop_all(bind=engine)
