"""NEXSYS configuration with environment variable support."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directories with env var override
DATA_DIR = Path(os.getenv("NEXSYS_DATA_DIR", Path.home() / ".nexsys"))

# Database configuration (SQLite with migrations support)
DATABASE_URL = os.getenv("NEXSYS_DATABASE_URL", f"sqlite:///{DATA_DIR}/nexus.db")
USE_SQLITE = os.getenv("NEXSYS_USE_SQLITE", "true").lower() == "true"

# File-based storage (legacy/backup)
GRAPH_FILE = DATA_DIR / "graph.json"
DOCUMENTS_FILE = DATA_DIR / "documents.json"
TASKS_FILE = DATA_DIR / "tasks.json"
AGENTS_FILE = DATA_DIR / "agents.json"
AUTH_FILE = DATA_DIR / "auth.json"
SKILLS_DIR = DATA_DIR / "skills"

# API Configuration
API_HOST = os.getenv("NEXSYS_API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("NEXSYS_API_PORT", "8420"))
FRONTEND_PORT = int(os.getenv("NEXSYS_FRONTEND_PORT", "5173"))
CORS_ORIGINS = os.getenv("NEXSYS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

# Security
SECRET_KEY = os.getenv("NEXSYS_SECRET_KEY", "")
TOKEN_EXPIRY_HOURS = int(os.getenv("NEXSYS_TOKEN_EXPIRY_HOURS", "24"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("NEXSYS_RATE_LIMIT", "60"))

# LLM Configuration
LLM_PROVIDER = os.getenv("NEXSYS_LLM_PROVIDER", "ollama")
LLM_MODEL = os.getenv("NEXSYS_LLM_MODEL", "llama3.1:8b")
LLM_API_KEY = os.getenv("NEXSYS_LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("NEXSYS_LLM_BASE_URL", "http://localhost:11434")

# Google Gemini API Key (for audio processing and advanced features)
GEMINI_API_KEY = os.getenv("NEXSYS_GEMINI_API_KEY", "")

# Apollo.io API Key (for contact/company search)
APOLLO_API_KEY = os.getenv("NEXSYS_APOLLO_API_KEY", "")

# Vector Store Configuration
VECTOR_STORE_TYPE = os.getenv("NEXSYS_VECTOR_STORE", "chroma")
CHROMA_PERSIST_DIR = DATA_DIR / "chroma_db"

# Logging
LOG_LEVEL = os.getenv("NEXSYS_LOG_LEVEL", "INFO")
LOG_FILE = DATA_DIR / "nexus.log" if os.getenv("NEXSYS_LOG_FILE", "true").lower() == "true" else None

# Features
ENABLE_AUTO_AGENT_RUN = os.getenv("NEXSYS_AUTO_AGENT_RUN", "false").lower() == "true"
ENABLE_WEBSOCKETS = os.getenv("NEXSYS_WEBSOCKETS", "true").lower() == "true"


def ensure_data_dir():
    """Ensure all required directories exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create log file directory if needed
    if LOG_FILE:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
