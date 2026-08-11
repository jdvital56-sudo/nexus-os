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
    import backend.services.vector_store as vec_svc
    import backend.core.auth as auth_mod

    monkeypatch.setattr(doc_svc, "DOCUMENTS_FILE", tmp_path / "documents.json")
    monkeypatch.setattr(task_svc, "TASKS_FILE", tmp_path / "tasks.json")
    monkeypatch.setattr(graph_svc, "GRAPH_FILE", tmp_path / "graph.json")
    monkeypatch.setattr(agent_svc, "AGENTS_FILE", tmp_path / "agents.json")
    monkeypatch.setattr(auth_mod, "AUTH_FILE", tmp_path / "auth.json")
    monkeypatch.setattr(skills_svc, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mem_svc, "MEMORY_FILE", tmp_path / "memory.json")
    monkeypatch.setattr(vec_svc, "VECTORS_FILE", tmp_path / "vectors.json")

    # Хранилища, появившиеся позже: без них тесты писали бы в реальный ~/.nexsys
    import backend.services.budget as budget_svc
    import backend.services.personas as persona_svc

    monkeypatch.setattr(persona_svc, "PERSONAS_FILE", tmp_path / "personas.json")
    monkeypatch.setattr(budget_svc, "SPEND_FILE", tmp_path / "llm_spend.json")

    # Векторная индексация каждого факта поднимает ChromaDB и растягивает
    # прогон с 17 секунд до четырёх минут — в тестах она не нужна
    monkeypatch.setattr(mem_svc, "INDEXING_ENABLED", False)

    import backend.services.wallet as wallet_svc
    monkeypatch.setattr(wallet_svc, "SERVICES_FILE", tmp_path / "services.json")

    import backend.services.dream as dream_svc
    monkeypatch.setattr(dream_svc, "FINDINGS_FILE", tmp_path / "dream_findings.json")
    monkeypatch.setattr(dream_svc, "BRIEF_FILE", tmp_path / "dream_brief.json")

    # Боевые ключи лежат в переменных окружения машины. Без этой заглушки
    # тесты ходили бы в реальные API за реальные деньги.
    for field in ("openai_api_key", "anthropic_api_key", "deepseek_api_key",
                  "llm_api_key", "gemini_api_key"):
        monkeypatch.setattr(cfg.settings, field, "")

    # Шина событий не должна протекать между тестами
    from backend.core import eventbus

    monkeypatch.setattr(eventbus, "_subscribers", [])
    monkeypatch.setattr(eventbus, "_loop", None)

    # Init files
    (tmp_path / "graph.json").write_text('{"nodes": [], "edges": []}')
    (tmp_path / "auth.json").write_text('{}')
    (tmp_path / "memory.json").write_text('[]')
    (tmp_path / "vectors.json").write_text('{"ids": [], "texts": [], "vectors": [], "metadata": []}')
    for f in ["documents.json", "tasks.json", "agents.json"]:
        (tmp_path / f).write_text("[]")

    # Ensure config's ensure_data_dir uses tmp_path
    original_ensure = cfg.ensure_data_dir
    def patched_ensure():
        tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cfg, "ensure_data_dir", patched_ensure)

    # Patch each service's ensure_data_dir reference
    for svc_mod in [doc_svc, task_svc, graph_svc, agent_svc, auth_mod, skills_svc, mem_svc, vec_svc]:
        if hasattr(svc_mod, 'ensure_data_dir'):
            monkeypatch.setattr(svc_mod, "ensure_data_dir", patched_ensure)

    yield tmp_path


@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app)
