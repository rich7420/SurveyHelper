# surveyHelper service image (worker + MCP server). The DB runs as the pgvector image.
FROM python:3.12-slim

# uv for fast, locked installs
RUN pip install --no-cache-dir uv

WORKDIR /app

# Install deps first (cached layer); --no-dev keeps test/eval tooling out of the image.
COPY pyproject.toml uv.lock README.md ./
COPY surveyhelper ./surveyhelper
RUN uv sync --frozen --no-dev

# venv binaries (python, surveyhelper-mcp, surveyhelper-scan) on PATH
ENV PATH="/app/.venv/bin:$PATH"

# Default command is the worker; compose overrides it for the MCP server.
CMD ["python", "-m", "surveyhelper.worker"]
