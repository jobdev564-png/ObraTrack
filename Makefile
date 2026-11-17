.PHONY: install run dev seed test

install:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements-dev.txt

run:
	.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

dev:
	.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

seed:
	.venv/bin/python -m app.seed

test:
	.venv/bin/python -m pytest -q
