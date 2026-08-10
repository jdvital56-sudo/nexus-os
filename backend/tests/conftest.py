"""Shared test fixtures."""
import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import json


@pytest.fixture(autouse=True)
def temp_data_dir(tmp_path, monkeypatch):
    """Redirect all data to a temp directory."""
    import backend.core.config as cfg

    # Patch all config paths
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "GRAPH_FILE", tmp_path / "graph.json")
    monkeypatch.setattr(cfg, "DOCUMENTS_FILE", tmp_path / "documents.json")
    monkeypatch.setattr(cfg, "TASKS_FILE", tmp_path / "tasks.json")
    monkeypatch.setattr(cfg, "AGENTS_FILE", tmp_path / "agents.json")
    monkeypatch.setattr(cfg, "AUTH_FILE", tmp_path / "auth.json")

    # Also patch the service modules directly since they may have cached references
    import backend.services.documents as doc_svc
    import backend.services.tasks as task_svc
    import backend.services.graph as graph_svc
    import backend.services.agents as agent_svc
    import backend.services.skills as skills_svc
    import backend.services.memory as mem_svc
    import backend.core.auth as auth_mod

    monkeypatch.setattr(doc_svc, "DOCUMENTS_FILE", tmp_path / "documents.json")
    monkeypatch.setattr(task_svc, "TASKS_FILE", tmp_path / "tasks.json")
    monkeypatch.setattr(graph_svc, "GRAPH_FILE", tmp_path / "graph.json")
    monkeypatch.setattr(agent_svc, "AGENTS_FILE", tmp_path / "agents.json")
    monkeypatch.setattr(auth_mod, "AUTH_FILE", tmp_path / "auth.json")
    monkeypatch.setattr(skills_svc, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mem_svc, "MEMORY_FILE", tmp_path / "memory.json")

    # Init files
    (tmp_path / "graph.json").write_text('{"nodes": [], "edges": []}')
    (tmp_path / "auth.json").write_text('{}')
    (tmp_path / "memory.json").write_text('[]')
    for f in ["documents.json", "tasks.json", "agents.json"]:
        (tmp_path / f).write_text("[]")

    # Ensure config's ensure_data_dir uses tmp_path
    original_ensure = cfg.ensure_data_dir
    def patched_ensure():
        tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cfg, "ensure_data_dir", patched_ensure)

    # Patch each service's ensure_data_dir reference
    for svc_mod in [doc_svc, task_svc, graph_svc, agent_svc, auth_mod, skills_svc, mem_svc]:
        if hasattr(svc_mod, 'ensure_data_dir'):
            monkeypatch.setattr(svc_mod, "ensure_data_dir", patched_ensure)

    yield tmp_path


@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app)
