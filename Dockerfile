# ── Stage: runtime ────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Don't buffer stdout/stderr — important for cloud log streaming
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies first (layer-cached when only code changes)
COPY backend/requirements.txt ./backend/requirements.txt
# Install CPU-only torch first (much smaller than CUDA build, fits free tier)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy the full project (backend package + trained RL models + agent)
COPY backend/     ./backend/
COPY rl/models/   ./rl/models/
COPY rl/agent.py  ./rl/agent.py

# Stub __init__.py so rl is a package root (lazy imports from simulation_manager)
RUN mkdir -p rl && touch rl/__init__.py

# Koyeb / Render inject PORT at runtime
EXPOSE 8000
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
