# ── Stage: runtime ────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Don't buffer stdout/stderr — important for cloud log streaming
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies first (layer-cached when only code changes)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy the full project (backend package + rl package for lazy RL imports)
COPY backend/ ./backend/
COPY rl/       ./rl/

# Create an empty __init__.py at root level so relative imports work
RUN touch __init__.py

# Koyeb / Render inject PORT at runtime
EXPOSE 8000
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
