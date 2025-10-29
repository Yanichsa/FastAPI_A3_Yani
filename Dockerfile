# ----- Base image pinned to 3.11.4 -----
ARG PYTHON_VERSION=3.11.4
FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

# Runtime deps (OpenMP for LightGBM/XGBoost wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user + workdir
RUN useradd -m -s /bin/bash appuser
WORKDIR /app

# Install Python deps first (better caching)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy app code (owned by appuser)
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser fetch/ ./fetch/
COPY --chown=appuser:appuser preprocessing/ ./preprocessing/
COPY --chown=appuser:appuser models/ /models/
COPY --chown=appuser:appuser pyproject.toml README.md ./

# Keep imports clean; align model path with COPY above
ENV PYTHONPATH="/app" \
    MODEL_PATH="/models/lgbm_final_ma_copy.joblib" \
    HOME="/home/appuser"

EXPOSE 8000
USER appuser

# Option A (simple): use UVicorn directly (Render sets $PORT)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]

# Option B (safer): handle PORT in Python and run module
#   In app/main.py add:
#   if __name__ == "__main__":
#       import os, uvicorn
#       uvicorn.run('app.main:app', host='0.0.0.0', port=int(os.getenv('PORT', '8000')))
# Then use:
# CMD ["python", "-m", "app.main"]
