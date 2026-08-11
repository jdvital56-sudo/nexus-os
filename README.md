# NEXSYS

Local-first AI agent operating system with knowledge graph, memory, and multi-agent orchestration.

## Features

- 🧠 **Knowledge Graph** — NetworkX-based graph with nodes, edges, and semantic relationships
- 🔍 **Vector Search** — ChromaDB integration with NumPy fallback for semantic search
- 🤖 **Multi-Agent System** — 6 specialized agents (Builder, Librarian, Reviewer, Researcher, Monitor, Jarvis)
- 💾 **Memory Layers** — Short-term, working, and long-term memory with confidence scoring
- 📚 **Document Management** — Import, tag, and link documents to knowledge graph
- ✅ **Task System** — Task creation, assignment, and tracking with priorities
- 🎯 **Skills Engine** — JSON-defined skill contracts for repeatable actions
- 🔌 **LLM Integration** — Support for Ollama, OpenAI, and Anthropic providers
- 🔒 **Secure Auth** — Token-based authentication with configurable expiry
- 📊 **Logging & Monitoring** — Configurable logging with file support

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- (Optional) Ollama for local LLM: `ollama run llama3.1:8b`

### Installation

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### Configuration

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

Key settings:
- `NEXSYS_LLM_PROVIDER` — Choose: `ollama`, `openai`, or `anthropic`
- `NEXSYS_VECTOR_STORE` — Choose: `chroma` or `numpy` (fallback)
- `NEXSYS_API_PORT` — Default: `8420`
- `NEXSYS_LOG_LEVEL` — Default: `INFO`

### Running

```bash
# Development mode (backend + frontend)
python -m cli.main start

# Or separately:
# Backend
cd backend && uvicorn main:app --reload --host 127.0.0.1 --port 8420

# Frontend
cd frontend && npm run dev
```

### Docker

```bash
docker-compose up -d
```

## CLI Commands

```bash
# Initialize project
nexsys init

# Start all services
nexsys start

# Health check
nexsys doctor

# Run specific agent
nexsys agent run librarian

# Execute skill
nexsys skill run publish-post --params '{"topic": "AI", "platform": "twitter"}'
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `/api/health` | Health check |
| `/api/documents` | Document CRUD + import |
| `/api/tasks` | Task management |
| `/api/graph` | Knowledge graph operations |
| `/api/agents` | Agent management + execution |
| `/api/memory` | Memory layers |
| `/api/vector-search` | Semantic search |
| `/api/skills` | Skill execution |
| `/api/docs` | Interactive API docs (Swagger) |
| `/api/redoc` | Alternative API docs (ReDoc) |

## Architecture

### Backend Stack
- **Framework**: FastAPI + Pydantic
- **Graph**: NetworkX
- **Vector Store**: ChromaDB (with NumPy fallback)
- **Storage**: JSON-хранилище (`data/`)
- **Auth**: JWT with python-jose

### Frontend Stack
- **Build**: Vite
- **Language**: TypeScript
- **UI**: React + Canvas visualization

### Agents

| Agent | Role | Responsibility |
|-------|------|----------------|
| **Builder** | Implementation | Executes build tasks, creates features |
| **Librarian** | Organization | Links documents to graph, manages tags |
| **Reviewer** | Quality | Checks for orphan nodes, flags issues |
| **Researcher** | Discovery | Identifies knowledge gaps, plans research |
| **Monitor** | Health | Detects anomalies, creates alerts |
| **Jarvis** | Orchestrator | Coordinates all agents, strategic decisions |

### Execution Cycle

Each agent follows the **O-O-T-A-V** cycle:
1. **Orient** — Read system state
2. **Observe** — Collect relevant data
3. **Think** — Plan actions
4. **Act** — Execute actions
5. **Verify** — Check results

## Skills System

Skills are JSON contracts defining repeatable workflows:

```json
{
  "name": "Publish Post",
  "description": "Create and publish a social media post",
  "category": "content",
  "steps": [
    {"action": "create_task", "params": {"title": "Draft post: {topic}", "tags": ["content"]}},
    {"action": "add_graph_node", "params": {"id": "post:{topic}", "label": "Post: {topic}"}},
    {"action": "log", "params": {"message": "Post created for {topic}"}}
  ]
}
```

Default skills:
- `publish-post` — Social media content creation
- `reply-comment` — Comment response drafting
- `crisis-escalate` — Emergency escalation workflow
- `collect-metrics` — Performance metrics gathering

## Vector Search

Two modes available:

### ChromaDB (Recommended)
```bash
NEXSYS_VECTOR_STORE=chroma
```
- Persistent storage
- Production-ready
- Automatic embeddings

### NumPy Fallback
```bash
NEXSYS_VECTOR_STORE=numpy
```
- No dependencies
- Uses sentence-transformers if available
- Falls back to text search

## LLM Providers

### Ollama (Local)
```env
NEXSYS_LLM_PROVIDER=ollama
NEXSYS_LLM_MODEL=llama3.1:8b
NEXSYS_LLM_BASE_URL=http://localhost:11434
```

### OpenAI
```env
NEXSYS_LLM_PROVIDER=openai
NEXSYS_LLM_MODEL=gpt-4o-mini
NEXSYS_LLM_API_KEY=sk-...
```

### Anthropic
```env
NEXSYS_LLM_PROVIDER=anthropic
NEXSYS_LLM_MODEL=claude-3-sonnet-20240229
NEXSYS_LLM_API_KEY=sk-ant-...
```

## Project Structure

```
nexus-os/
├── backend/
│   ├── api/          # REST endpoints
│   ├── core/         # Config, auth, errors
│   ├── models/       # Pydantic schemas
│   ├── services/     # Business logic
│   └── tests/        # Test suite
├── frontend/
│   ├── src/          # React components
│   └── public/       # Static assets
├── cli/              # Command-line interface
├── nexus-os/         # Core OS modules
├── .env.example      # Environment template
├── docker-compose.yml
└── README.md
```

## Development

### Code Quality
```bash
# Install dev dependencies
pip install ruff black mypy pytest-cov

# Run linters
ruff check backend/
black --check backend/
mypy backend/

# Run tests
pytest backend/tests/ --cov=backend
```

### Pre-commit Hooks
```bash
pip install pre-commit
pre-commit install
```

## Troubleshooting

### Token not showing
Check `~/.nexsys/auth.json` for your auth token.

### ChromaDB errors
Ensure ChromaDB is installed: `pip install chromadb`

### LLM connection failed
- Verify Ollama is running: `ollama list`
- Check API key for OpenAI/Anthropic
- Test connection: `curl http://localhost:11434/api/tags`

### Port conflicts
Change ports in `.env`:
```env
NEXSYS_API_PORT=8421
NEXSYS_FRONTEND_PORT=5174
```

## License

Private

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run tests before submitting PR
4. Update documentation as needed
