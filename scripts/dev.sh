#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
uv sync --project backend --locked --python 3.12
npm --prefix frontend ci
npm --prefix extension ci
uv run --project backend --no-sync uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT INT TERM
npm --prefix frontend run dev
