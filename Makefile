.PHONY: venv install test lint fmt preview fetch build-data clean

venv:
	uv venv

install: venv
	uv pip install -e ".[dev]"

build-data:
	.venv/bin/dailyprint build-data

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .

fmt:
	.venv/bin/ruff format .

preview:
	.venv/bin/dailyprint preview -o preview.txt

fetch:
	.venv/bin/dailyprint fetch --count 3 --images

clean:
	rm -rf .venv .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
