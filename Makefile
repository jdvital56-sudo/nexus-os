.PHONY: install test run dev docker clean hooks

# Git Bash/WSL на Windows не имеют python3 — берём то, что доступно (I-8)
PYTHON ?= $(shell command -v python3 2>/dev/null || command -v python)

install:
	$(PYTHON) -m pip install -r backend/requirements.txt
	$(PYTHON) -c "from pathlib import Path; [Path(p).mkdir(parents=True, exist_ok=True) for p in ('artifacts', 'documents/hermes', Path.home() / '.nexsys')]"
	cd frontend && npm install
	@echo "Установка завершена. Дальше: заполните .env по README_HERMES.md, затем make run"

test:
	$(PYTHON) -m pytest

# Заслон от `git add -A`: несколько сессий часто идут в одном дереве, и
# слепой коммит утаскивает чужую незакоммиченную работу (см. CLAUDE.md)
hooks:
	cp scripts/pre-commit .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "Хук поставлен. Большой коммит осознанно: NEXUS_BIG_COMMIT=1 git commit ..."

run:
	$(PYTHON) -m cli.main start

# Один uvicorn-worker: JSON-хранилище и APScheduler не переживут конкурентных писателей (I-3)
dev:
	$(PYTHON) -m uvicorn backend.main:app --reload --workers 1 --port 8420 &
	cd frontend && npm run dev

docker:
	docker-compose up --build

clean:
	rm -rf __pycache__ .pytest_cache frontend/node_modules frontend/dist
	find . -name "*.pyc" -delete
