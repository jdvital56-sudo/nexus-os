"""NEXSYS CLI — init / start / doctor."""
import sys
import os
import json
import subprocess
import shutil
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

app = typer.Typer(name="nexsys", help="NEXSYS — Local-first AI agent OS")

DATA_DIR = Path.home() / ".nexsys"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@app.command()
def init():
    """Initialize NEXSYS data directory."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for f in ["graph.json", "documents.json", "tasks.json", "agents.json"]:
        p = DATA_DIR / f
        if not p.exists():
            p.write_text("[]")
            typer.echo(f"  Created {p}")
    typer.echo(f"[NEXSYS] Initialized at {DATA_DIR}")


@app.command()
def start(host: str = "127.0.0.1", port: int = 8420, frontend: bool = True):
    """Start NEXSYS backend (and optionally frontend)."""
    init()

    typer.echo(f"[NEXSYS] Starting backend on {host}:{port}...")

    # Start backend
    backend_cmd = [
        sys.executable, "-m", "uvicorn",
        "backend.main:app",
        "--host", host,
        "--port", str(port),
        "--reload",
    ]

    if frontend:
        frontend_dir = PROJECT_ROOT / "frontend"
        if (frontend_dir / "package.json").exists():
            typer.echo("[NEXSYS] Starting frontend...")
            subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=frontend_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            typer.echo(f"[NEXSYS] Frontend at http://localhost:5173")

    typer.echo(f"[NEXSYS] Backend at http://{host}:{port}")
    typer.echo(f"[NEXSYS] API docs at http://{host}:{port}/docs")
    subprocess.run(backend_cmd)


@app.command()
def import_docs(path: str, source: str = "file"):
    """Import documents from a directory of markdown files."""
    init()
    sys.path.insert(0, str(PROJECT_ROOT))
    from backend.services.documents import import_markdown_dir
    try:
        docs = import_markdown_dir(path)
        typer.echo(f"[NEXSYS] Imported {len(docs)} documents from {path}")
        for d in docs[:5]:
            typer.echo(f"  - {d.title} ({len(d.tags)} tags)")
        if len(docs) > 5:
            typer.echo(f"  ... and {len(docs) - 5} more")
    except Exception as e:
        typer.echo(f"[NEXSYS] Error: {e}")


@app.command()
def memory_stats():
    """Show memory system statistics."""
    init()
    sys.path.insert(0, str(PROJECT_ROOT))
    from backend.services.memory import get_stats
    stats = get_stats()
    typer.echo(f"\n[NEXSYS Memory]\n")
    typer.echo(f"  Total facts: {stats['total']}")
    typer.echo(f"  Active: {stats['active']}")
    typer.echo(f"  Expired: {stats['expired']}")
    typer.echo(f"  Avg confidence: {stats['avg_confidence']}")
    typer.echo(f"\n  By layer:")
    for layer, count in stats.get('by_layer', {}).items():
        typer.echo(f"    {layer}: {count}")


@app.command()
def doctor():
    """Health check — verify NEXSYS installation."""
    checks = []

    # 1. Python version
    v = sys.version_info
    ok = v >= (3, 11)
    checks.append(("Python >= 3.11", ok, f"{v.major}.{v.minor}.{v.micro}"))

    # 2. Dependencies
    for mod in ["fastapi", "uvicorn", "pydantic", "networkx", "typer"]:
        try:
            __import__(mod)
            checks.append((f"Module: {mod}", True, "installed"))
        except ImportError:
            checks.append((f"Module: {mod}", False, "MISSING"))

    # 3. Data directory
    checks.append(("Data dir exists", DATA_DIR.exists(), str(DATA_DIR)))

    # 4. Data files
    for f in ["graph.json", "documents.json", "tasks.json", "agents.json"]:
        p = DATA_DIR / f
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                checks.append((f"Data: {f}", True, f"{len(data)} records"))
            except Exception as e:
                checks.append((f"Data: {f}", False, f"corrupt: {e}"))
        else:
            checks.append((f"Data: {f}", False, "missing"))

    # 5. Port check
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        port_ok = s.connect_ex(("127.0.0.1", 8420)) != 0
    checks.append(("Port 8420 free", port_ok, "available" if port_ok else "IN USE"))

    # 6. Frontend
    fe_pkg = PROJECT_ROOT / "frontend" / "package.json"
    checks.append(("Frontend package.json", fe_pkg.exists(), str(fe_pkg)))

    # Print
    typer.echo("\n[NEXSYS Doctor]\n")
    all_ok = True
    for name, ok, detail in checks:
        icon = "✓" if ok else "✗"
        typer.echo(f"  {icon} {name}: {detail}")
        if not ok:
            all_ok = False

    typer.echo()
    if all_ok:
        typer.echo("[NEXSYS] All checks passed.")
    else:
        typer.echo("[NEXSYS] Some checks failed. Run `nexsys init` or install missing deps.")


if __name__ == "__main__":
    app()
