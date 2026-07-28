#!/bin/sh
set -e

uv run --frozen --no-dev python -m sac.infrastructure.migrate all
uv run --frozen --no-dev python -m sac.infrastructure.seed
exec uv run --frozen --no-dev uvicorn sac.main:app --host 0.0.0.0 --port 8000 --reload
