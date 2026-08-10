"""Obsidian sync tests."""
import os


def test_obsidian_status(client):
    r = client.get("/api/obsidian/status")
    assert r.status_code == 200
    data = r.json()
    assert "files_synced" in data


def test_obsidian_scan_nonexistent(client):
    r = client.post("/api/obsidian/scan", json={"vault_path": "/nonexistent/path"})
    assert r.status_code == 200
    data = r.json()
    assert "error" in data


def test_obsidian_sync_nonexistent(client):
    r = client.post("/api/obsidian/sync", json={"vault_path": "/nonexistent/path"})
    assert r.status_code == 200
    data = r.json()
    assert "error" in data


def test_obsidian_scan_real_vault(client, tmp_path):
    """Create a mini vault and scan it."""
    vault = tmp_path / "vault"
    vault.mkdir()

    # Create some notes
    (vault / "note1.md").write_text("# Note 1\n\nThis is about #ai and #graphs.\n\nSee also [[note2]].")
    (vault / "note2.md").write_text("# Note 2\n\nThis references [[note1]] and [[note3]].\n\n#ai #memory")
    (vault / "sub").mkdir()
    (vault / "sub" / "note3.md").write_text("# Note 3\n\nSubfolder note. #graphs")

    r = client.post("/api/obsidian/scan", json={"vault_path": str(vault)})
    assert r.status_code == 200
    data = r.json()
    assert data["total_notes"] == 3
    assert data["unique_tags"] >= 2  # ai, graphs
    assert data["unique_wikilinks"] >= 2  # note1, note2, note3


def test_obsidian_sync_real_vault(client, tmp_path):
    """Create a mini vault and sync it."""
    vault = tmp_path / "vault"
    vault.mkdir()

    (vault / "hello.md").write_text("# Hello World\n\nFirst note. #test\n\n[[world]]")
    (vault / "world.md").write_text("# World\n\nSecond note. #test #demo\n\n[[hello]]")

    r = client.post("/api/obsidian/sync", json={"vault_path": str(vault)})
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 2
    assert data["graph_nodes_added"] >= 2
    assert data["graph_edges_added"] >= 2

    # Check graph grew
    stats = client.get("/api/graph/stats").json()
    assert stats["nodes"] > 0

    # Check documents were created
    docs = client.get("/api/documents").json()
    assert len(docs) >= 2

    # Run again — should skip (incremental)
    r = client.post("/api/obsidian/sync", json={"vault_path": str(vault)})
    data = r.json()
    assert data["skipped"] == 2
    assert data["imported"] == 0


def test_obsidian_reset(client):
    r = client.post("/api/obsidian/reset")
    assert r.status_code == 200
    assert r.json()["ok"] is True
