FROM node:22-slim AS web
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /usr/local/bin/uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN uv sync --project backend --locked --no-dev
COPY backend/app ./backend/app
COPY backend/migrations ./backend/migrations
COPY backend/alembic.ini ./backend/alembic.ini
COPY --from=web /build/frontend/dist ./frontend/dist
COPY scripts ./scripts
COPY config ./config
ENV DATABASE_URL=sqlite+aiosqlite:////data/campus.db AGENT_DB_PATH=/data/agent.db UPLOAD_DIR=/data/uploads SECURE_COOKIE=true
RUN mkdir /data && useradd --uid 10001 --create-home campus && chown -R campus /data /app
USER campus
EXPOSE 8000
CMD ["/app/backend/.venv/bin/uvicorn","app.main:create_app","--factory","--app-dir","backend","--host","0.0.0.0","--port","8000"]
