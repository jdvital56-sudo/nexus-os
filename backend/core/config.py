"""NEXSYS configuration."""
from pathlib import Path

DATA_DIR = Path.home() / ".nexsys"
GRAPH_FILE = DATA_DIR / "graph.json"
DOCUMENTS_FILE = DATA_DIR / "documents.json"
TASKS_FILE = DATA_DIR / "tasks.json"
AGENTS_FILE = DATA_DIR / "agents.json"
AUTH_FILE = DATA_DIR / "auth.json"

API_HOST = "127.0.0.1"
API_PORT = 8420
FRONTEND_PORT = 5173

def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
