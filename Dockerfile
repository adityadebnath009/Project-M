# Dockerfile for Project-M MCP server verification and containerized execution
FROM python:3.12-slim

# Install uv from official astral image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency specifications
COPY pyproject.toml uv.lock ./

# Install project dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and metadata
COPY README.md LICENSE ./
COPY src/ ./src/

# Install the application
RUN uv sync --frozen --no-dev

# Set PATH so project-m executable is directly available
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Default command runs the MCP server on stdio
ENTRYPOINT ["project-m", "run"]
