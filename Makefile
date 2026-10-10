REGION ?= manhattan
PY = uv run python

.PHONY: setup lint test data scenarios web build xval demo

setup:
	uv sync
	cd web && npm install

lint:
	uv run ruff check pipeline tests
	cd web && npx tsc --noEmit

test:
	uv run pytest -q
	cd web && npx vitest run

data:
	$(PY) -m gyeol.cli data --region $(REGION)

scenarios:
	$(PY) -m gyeol.cli scenarios

demo:
	$(PY) -m gyeol.cli demo --region $(REGION)

xval:
	$(PY) -m gyeol.cli xval --region $(REGION)

web:
	cd web && npx vite

build:
	cd web && npx vite build
