.PHONY: install test run dev docker clean

install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

test:
	python3 -m pytest backend/tests/ -v

run:
	python3 -m cli.main start

dev:
	python3 -m uvicorn backend.main:app --reload --port 8420 &
	cd frontend && npm run dev

docker:
	docker-compose up --build

clean:
	rm -rf __pycache__ .pytest_cache node_modules dist
	find . -name "*.pyc" -delete
