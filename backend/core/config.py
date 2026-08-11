"""NEXSYS configuration with environment variable support."""
import os
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel

# Строго до объявления Settings: значения полей вычисляются при создании
# класса, поэтому .env, загруженный ниже по файлу, туда уже не попадёт.
load_dotenv()


class Settings(BaseModel):
    """Settings class for NEXSYS configuration."""
    
    # Base directories with env var override
    data_dir: Path = Path(os.getenv("NEXSYS_DATA_DIR", Path.home() / ".nexsys"))
    
    # File-based storage (JSON)
    graph_file: Path = None  # Will be set in __init__
    documents_file: Path = None
    tasks_file: Path = None
    agents_file: Path = None
    auth_file: Path = None
    skills_dir: Path = None
    
    # API Configuration
    api_host: str = os.getenv("NEXSYS_API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("NEXSYS_API_PORT", "8420"))
    frontend_port: int = int(os.getenv("NEXSYS_FRONTEND_PORT", "5173"))
    cors_origins: list = os.getenv("NEXSYS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    
    # Security
    secret_key: str = os.getenv("NEXSYS_SECRET_KEY", "")
    token_expiry_hours: int = int(os.getenv("NEXSYS_TOKEN_EXPIRY_HOURS", "24"))
    rate_limit_per_minute: int = int(os.getenv("NEXSYS_RATE_LIMIT", "60"))
    
    # LLM Configuration
    llm_provider: str = os.getenv("NEXSYS_LLM_PROVIDER", "ollama")
    llm_model: str = os.getenv("NEXSYS_LLM_MODEL", "llama3.1:8b")
    llm_api_key: str = os.getenv("NEXSYS_LLM_API_KEY", "")
    llm_base_url: str = os.getenv("NEXSYS_LLM_BASE_URL", "http://localhost:11434")
    
    # Ключи провайдеров Пантеона (имена из README_HERMES, не переименовывать до PR-25)
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")

    # Дневной потолок расходов на LLM в долларах (I-4)
    daily_llm_budget_usd: float = float(os.getenv("NEXUS_DAILY_LLM_BUDGET_USD", "5"))

    # Google Gemini API Key (for audio processing and advanced features)
    gemini_api_key: str = os.getenv("NEXSYS_GEMINI_API_KEY", "")
    
    # Apollo.io API Key (for contact/company search)
    apollo_api_key: str = os.getenv("NEXSYS_APOLLO_API_KEY", "")
    
    # Telegram Configuration
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_allowed_user_id: str = os.getenv("TELEGRAM_ALLOWED_USER_ID", "")
    
    # Vector Store Configuration
    vector_store_type: str = os.getenv("NEXSYS_VECTOR_STORE", "chroma")
    chroma_persist_dir: Path = None  # Will be set in __init__
    
    # Logging
    log_level: str = os.getenv("NEXSYS_LOG_LEVEL", "INFO")
    log_file: Optional[Path] = None
    
    # Features
    enable_auto_agent_run: bool = os.getenv("NEXSYS_AUTO_AGENT_RUN", "false").lower() == "true"
    enable_websockets: bool = os.getenv("NEXSYS_WEBSOCKETS", "true").lower() == "true"
    
    def __init__(self, **data):
        super().__init__(**data)
        # Set derived paths
        self.graph_file = self.data_dir / "graph.json"
        self.documents_file = self.data_dir / "documents.json"
        self.tasks_file = self.data_dir / "tasks.json"
        self.agents_file = self.data_dir / "agents.json"
        self.auth_file = self.data_dir / "auth.json"
        self.skills_dir = self.data_dir / "skills"
        self.chroma_persist_dir = self.data_dir / "chroma_db"
        
        if os.getenv("NEXSYS_LOG_FILE", "true").lower() == "true":
            self.log_file = self.data_dir / "nexus.log"
    
    def ensure_data_dir(self):
        """Ensure all required directories exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
        
        # Create log file directory if needed
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()


# Legacy compatibility - keep old variable names for backward compatibility
DATA_DIR = settings.data_dir
GRAPH_FILE = settings.graph_file
DOCUMENTS_FILE = settings.documents_file
TASKS_FILE = settings.tasks_file
AGENTS_FILE = settings.agents_file
AUTH_FILE = settings.auth_file
SKILLS_DIR = settings.skills_dir
API_HOST = settings.api_host
API_PORT = settings.api_port
FRONTEND_PORT = settings.frontend_port
CORS_ORIGINS = settings.cors_origins
SECRET_KEY = settings.secret_key
TOKEN_EXPIRY_HOURS = settings.token_expiry_hours
RATE_LIMIT_PER_MINUTE = settings.rate_limit_per_minute
LLM_PROVIDER = settings.llm_provider
LLM_MODEL = settings.llm_model
LLM_API_KEY = settings.llm_api_key
LLM_BASE_URL = settings.llm_base_url
GEMINI_API_KEY = settings.gemini_api_key
APOLLO_API_KEY = settings.apollo_api_key
VECTOR_STORE_TYPE = settings.vector_store_type
CHROMA_PERSIST_DIR = settings.chroma_persist_dir
LOG_LEVEL = settings.log_level
LOG_FILE = settings.log_file
ENABLE_AUTO_AGENT_RUN = settings.enable_auto_agent_run
ENABLE_WEBSOCKETS = settings.enable_websockets


def ensure_data_dir():
    """Ensure all required directories exist."""
    settings.ensure_data_dir()
