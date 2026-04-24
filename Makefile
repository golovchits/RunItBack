.PHONY: install fmt lint test dev create-agents create-env clean

install:
	uv sync --all-extras

fmt:
	uv run ruff format .

lint:
	uv run ruff check .
	uv run mypy backend

test:
	uv run pytest

dev:
	uv run uvicorn backend.main:app \
	  --reload --reload-dir backend --reload-dir scripts \
	  --host 0.0.0.0 --port 8000

create-agents:
	uv run python scripts/create_agents.py

create-env:
	uv run python scripts/create_environment.py

clean:
	rm -rf .venv .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
