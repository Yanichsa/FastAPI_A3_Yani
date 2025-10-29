# -----------------------------------------------------------------------------
# Base image (pin if you need an exact patch)
# -----------------------------------------------------------------------------
ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim AS base

# Prevents Python from buffering logs
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps (LightGBM needs a compiler + OpenMP)
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      gcc \
      g++ \
      libgomp1 \
      wget \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m appuser
WORKDIR /app

# -----------------------------------------------------------------------------
# Copy & install dependencies
# (faster builds if you copy only requirement files first)
# -----------------------------------------------------------------------------
COPY requirements.txt ./requirements.txt
# If you have a constraints file, add:  COPY constraints.txt ./constraints.txt
RUN pip install --upgrade pip \
 && pip install -r requirements.txt
 # If using constraints:  && pip install -r requirements.txt -c constraints.txt

# -----------------------------------------------------------------------------
# Copy application code
# -----------------------------------------------------------------------------
# Keep paths matching your compose mounts and imports
COPY app/ ./app/
COPY fetch/ ./fetch/
COPY preprocessing/ ./preprocessing/
COPY models/ ./models/
COPY pyproject.toml ./pyproject.toml
COPY README.md ./README.md

# Optional: set default envs (can be overridden by docker-compose or Render)
ENV PYTHONPATH="/" \
    MODEL_PATH="/models/lgbm_final_ma_copy.joblib"

# Expose the port Uvicorn will bind to (Render uses $PORT)
EXPOSE 8000

# Switch to non-root
USER appuser

# -----------------------------------------------------------------------------
# Default command (override in docker-compose.yml if you want --reload)
# Uses $PORT when provided (Render sets this), falls back to 8000 locally.
# -----------------------------------------------------------------------------
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
