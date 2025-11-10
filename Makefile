PY=python3

venv:
	$(PY) -m venv .venv && . .venv/bin/activate && pip install -U pip

install:
	. .venv/bin/activate && pip install -r services/mcp-server/requirements.txt && pip install -r services/contributor-agent/requirements.txt && pip install pytest

run-local:
	. .venv/bin/activate && PYTHONPATH=. $(PY) services/mcp-server/app.py

test:
	. .venv/bin/activate && pytest -q

docker:
	docker build -t mcp-server:dev services/mcp-server
	docker build -t contributor-agent:dev services/contributor-agent

compose-up:
	docker compose up -d

compose-down:
	docker compose down
