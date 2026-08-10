# NEXSYS

Local-first AI agent operating system with knowledge graph, memory, and multi-agent orchestration.

## Quick Start

```bash
# Install
cd backend && pip install -r requirements.txt
cd ../frontend && npm install

# Run
cd .. && python -m cli.main start
```

## Architecture

- **Backend**: FastAPI + Pydantic + NetworkX
- **Frontend**: Vite + TypeScript + Canvas
- **CLI**: Typer
- **Storage**: Local JSON/SQLite (local-first)

## CLI Commands

- `nexsys init` — Initialize project structure
- `nexsys start` — Start backend + frontend
- `nexsys doctor` — Health check

## API Endpoints

- `/api/documents` — Document CRUD + import
- `/api/tasks` — Task management
- `/api/graph` — Knowledge graph operations
- `/api/agents` — Agent management + execution

## Agents

Six roles: Builder, Librarian, Reviewer, Researcher, Monitor, Jarvis

## License

Private
