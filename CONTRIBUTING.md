# Contributing to NEXSYS

## Development Setup

```bash
# Clone and setup
git clone <repo>
cd nexus-os
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r backend/requirements.txt

# Install dev tools
pip install ruff black mypy pre-commit pytest-cov

# Setup pre-commit hooks
pre-commit install
```

## Code Quality

```bash
# Linting
ruff check backend/
black --check backend/
mypy backend/

# Auto-fix
ruff check --fix backend/
black backend/

# Run tests with coverage
pytest backend/tests/ --cov=backend --cov-report=html
```

## Architecture Guidelines

### Services Layer
- Each service handles one domain (documents, tasks, graph, etc.)
- Services use file-based storage with JSON
- Services should be stateless between calls
- Use dependency injection for testability

### API Layer
- RESTful endpoints under `/api/`
- Use Pydantic models for validation
- Return consistent error formats
- Document with OpenAPI/Swagger

### Agent System
- Agents follow Orient-Observe-Think-Act-Verify cycle
- Each role has specific responsibilities
- Jarvis orchestrates other agents
- Skills define repeatable workflows

## Testing

```bash
# All tests
pytest backend/tests/ -v

# Specific test
pytest backend/tests/test_graph.py::test_add_node -v

# With coverage
pytest backend/tests/ --cov=backend --cov-report=term-missing
```

## Git Workflow

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes with tests
3. Run linters and fix issues
4. Commit with clear messages
5. Open pull request

## Adding New Features

1. **New Service**: Create in `backend/services/`, add tests
2. **New API**: Add endpoint in `backend/api/`, document in OpenAPI
3. **New Agent Role**: Implement 5-phase cycle in `agent_engine.py`
4. **New Skill**: Add JSON contract to skills directory

## Common Issues

### Disk Space
Clear ChromaDB cache: `rm -rf ~/.cache/chroma`

### Import Errors
Ensure you're in the project root and venv is activated

### Test Failures
Tests use temp directories, ensure write permissions
