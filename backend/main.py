"""NEXSYS — FastAPI application entry point."""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import (
    API_HOST, 
    API_PORT, 
    CORS_ORIGINS, 
    LOG_LEVEL, 
    LOG_FILE,
    DATA_DIR,
    ensure_data_dir
)
from .core.errors import NexsysError, nexsys_error_handler, generic_error_handler
from .core.auth import init_auth
from .api import documents, tasks, graph, agents, webhooks, skills, calendar, obsidian, pipeline, memory, events, vector_search, fireflies, telephony, personas, dream

# Configure logging
log_config = {
    "level": getattr(logging, LOG_LEVEL, logging.INFO),
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
}
if LOG_FILE:
    log_config["filename"] = str(LOG_FILE)
    logging.basicConfig(**log_config)
else:
    logging.basicConfig(**log_config)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="NEXSYS",
    description="Local-first AI agent operating system",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS — configurable origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Unified error format
app.add_exception_handler(NexsysError, nexsys_error_handler)
app.add_exception_handler(Exception, generic_error_handler)

# Routes
app.include_router(documents.router)
app.include_router(tasks.router)
app.include_router(graph.router)
app.include_router(agents.router)
app.include_router(webhooks.router)
app.include_router(skills.router)
app.include_router(calendar.router)
app.include_router(obsidian.router)
app.include_router(pipeline.router)
app.include_router(memory.router)
app.include_router(events.router)
app.include_router(vector_search.router)
app.include_router(fireflies.router)
app.include_router(telephony.router)
app.include_router(personas.router)
app.include_router(dream.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "nexsys", "version": "0.1.0"}


@app.on_event("startup")
async def startup():
    """Initialize application on startup."""
    ensure_data_dir()
    token = init_auth()

    # Шина событий: запоминаем именно работающий цикл — emit() зовут из
    # рабочих потоков (asyncio.to_thread), оттуда его иначе не достать
    import asyncio as _asyncio

    from .core import eventbus

    eventbus.bind_loop(_asyncio.get_running_loop())
    events.install()

    # Create default skills
    try:
        from .services.skills import create_default_skills
        create_default_skills()
        logger.info("Default skills created successfully")
    except Exception as e:
        logger.warning(f"Failed to create default skills: {e}")

    # Ночная аналитика живёт в этом же процессе: при нескольких воркерах
    # APScheduler запустил бы джобу в каждом (I-3, риск R-4)
    try:
        from .agents.dream_cadence import start_dream_cadence
        start_dream_cadence()
    except Exception as e:
        logger.warning(f"Dream Cadence не запущен: {e}")


    # Log startup info (without exposing token in production)
    logger.info(f"NEXSYS v0.1.0 starting on {API_HOST}:{API_PORT}")
    logger.info(f"CORS allowed origins: {', '.join(CORS_ORIGINS)}")
    
    # Only print token in development (check via environment)
    import os
    if os.getenv("NEXSYS_ENV", "development") == "development":
        print(f"[NEXSYS] Auth token: {token}")
    else:
        print(f"[NEXSYS] Auth token initialized (check {DATA_DIR / 'auth.json'})")
    
    print(f"[NEXSYS] API running at http://{API_HOST}:{API_PORT}")
    print(f"[NEXSYS] Docs available at http://{API_HOST}:{API_PORT}/api/docs")
