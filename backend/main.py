"""NEXSYS — FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.errors import NexsysError, nexsys_error_handler, generic_error_handler
from .core.auth import init_auth
from .api import documents, tasks, graph, agents

app = FastAPI(
    title="NEXSYS",
    description="Local-first AI agent operating system",
    version="0.1.0",
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "nexsys", "version": "0.1.0"}


@app.on_event("startup")
def startup():
    token = init_auth()
    print(f"[NEXSYS] Auth token: {token}")
    print(f"[NEXSYS] API running at http://127.0.0.1:8420")
