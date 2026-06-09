.PHONY: db schema mcp worker scheduler verify test fmt

DSN ?= postgresql://surveyhelper:surveyhelper@localhost:5544/surveyhelper

db:  ## start the dedicated pgvector Postgres
	docker run -d --name surveyhelper-pg \
	  -e POSTGRES_PASSWORD=surveyhelper -e POSTGRES_USER=surveyhelper -e POSTGRES_DB=surveyhelper \
	  -p 5544:5432 pgvector/pgvector:pg16

schema:  ## apply schema.sql
	docker exec -i surveyhelper-pg psql -U surveyhelper -d surveyhelper -v ON_ERROR_STOP=1 < schema.sql

mcp:  ## run the MCP server (streamable-http :8765)
	uv run surveyhelper-mcp

worker:  ## run the background worker
	uv run python -m surveyhelper.worker

scheduler:  ## run the daily proactive-scan scheduler
	uv run python -m surveyhelper.scheduler

verify:  ## first-run self-test (surveys a known paper, prints the card)
	uv run surveyhelper-verify

test:  ## run unit tests
	uv run pytest -q
