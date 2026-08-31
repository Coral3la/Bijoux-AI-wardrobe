# syntax=docker/dockerfile:1.7

# ---------- Stage 1: build the Angular frontend ----------
FROM node:24-alpine AS frontend-build
WORKDIR /frontend

# Install deps against the committed lockfile first so this layer caches.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Then bring the rest of the frontend in and produce the production bundle.
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: Python runtime that serves API + built SPA ----------
FROM python:3.14-slim
WORKDIR /app

# Backend deps first, so a code-only change doesn't reinstall pip packages.
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# The whole backend at /app, so CWD matches how uvicorn/alembic are run
# locally (pydantic-settings reads .env relative to CWD — .env is not baked
# into the image, all config comes from Render's environment variables).
COPY backend/ ./

# The built Angular bundle at /app/static — app/main.py mounts it from there.
COPY --from=frontend-build /frontend/dist/bijoux/browser ./static

ENV PORT=8000
EXPOSE 8000

# Shell form so ${PORT} is expanded at runtime (Render injects it).
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
