.PHONY: test eval ingest run lint docker-build docker-up

PYTHON = venv/bin/python
PYTEST = venv/bin/pytest

test:
	PYTHONPATH=. $(PYTEST) tests/ -v

eval:
	PYTHONPATH=. $(PYTHON) eval/run_eval.py

ingest:
	PYTHONPATH=. $(PYTHON) app/rag/chunker.py

lint:
	PYTHONPATH=. $(PYTHON) -m compileall -q app/ tests/

run:
	PYTHONPATH=. $(PYTHON) app/main.py

docker-build:
	docker compose build

docker-up:
	docker compose up -d
