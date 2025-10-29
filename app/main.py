from __future__ import annotations

import os
from typing import List, Optional, Literal

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------------------
# Feature engineering helpers (force-UTC inside ensure_time_and_sort in your file)
# --------------------------------------------------------------------------------------
try:
    from preprocessing.feature_engineering import (
        FINAL_FEATURES,
        ensure_time_and_sort,
        build_features_from_ohlcv,
    )
except Exception as e:
    raise RuntimeError(f"Failed to import preprocessing.feature_engineering: {e}")

# --------------------------------------------------------------------------------------
# SOL-only fetcher (Kraken public OHLC)
# Keep only ONE fetcher module in your repo. We import this one explicitly.
# --------------------------------------------------------------------------------------
try:
    from fetch.kraken_ohlc_solusd import get_recent_candles as fetch_candles  # type: ignore
except Exception as e:
    fetch_candles = None  # we'll error nicely in the endpoint

# --------------------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------------------
MODEL_PATH = os.getenv("MODEL_PATH", "models/lgbm_final_ma_copy.joblib")
MODEL_TARGET_MODE: Literal["level", "delta", "logdiff"] = os.getenv("MODEL_TARGET_MODE", "level").lower()  # how the model was trained

# --------------------------------------------------------------------------------------
# Load model once (ensure LightGBM + OpenMP present)
# --------------------------------------------------------------------------------------
try:
    import lightgbm as lgb  # required for joblib to unpickle LGBMRegressor
except ModuleNotFoundError as e:
    raise RuntimeError(
        "LightGBM not installed. Install it in this env (conda-forge recommended):\n"
        "  conda install -c conda-forge lightgbm llvm-openmp\n"
        "or if using pip + Homebrew:\n  pip install lightgbm && brew install libomp\n"
    ) from e

try:
    model = joblib.load(MODEL_PATH)
except OSError as e:
    raise RuntimeError(
        f"Failed to load model from {MODEL_PATH}: {e}\n"
        "If error mentions libomp.dylib on macOS, install OpenMP runtime:\n"
        "  conda install -c conda-forge llvm-openmp\n  # or: brew install libomp"
    )
except Exception as e:
    raise RuntimeError(f"Failed to load model from {MODEL_PATH}: {e}")

# --------------------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------------------
class Candle(BaseModel):
    timeOpen: str = Field(..., description="ISO timestamp of the bar open time (e.g., 2025-09-30T00:00:00Z)")
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None

class PredictRequest(BaseModel):
    candles: List[Candle] = Field(..., description="At least 21 most recent OHLCV rows, ascending by timeOpen recommended")
    target_mode: Optional[Literal["level", "delta", "logdiff"]] = Field(
        None, description="Override the server default. 'level' predicts next-day high directly; 'delta' predicts add-on to last high; 'logdiff' predicts log(h_{t+1})-log(h_t)."
    )

class PredictResponse(BaseModel):
    predicted_high_next_day: float
    target_mode: Literal["level", "delta", "logdiff"]
    last_known_high: Optional[float] = None
    features_used: List[str]
    feature_vector_tail: dict

class PredictTokenResponse(PredictResponse):
    token: str
    history_rows_used: int

# --------------------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------------------
app = FastAPI(title="SOL Next-Day High Predictor", version="1.1.0")

@app.get("/")
def root():
    return {
        "project": "SOL/crypto next-day High predictor",
        "endpoints": {
            "GET /": "This message",
            "GET /health": "Liveness check",
            "GET /model/info": "Model & features metadata",
            "POST /predict": "Predict next-day high from provided OHLCV rows",
            "GET /predict/sol": "Fetch candles for SOL and predict next-day high",
            "GET /predict/sol/at": "Anchor by date, predict the next-day high",
        },
        "expected_input": {
            "candles": "Array of OHLCV dicts with fields: timeOpen, open, high, low, close, (optional) volume",
            "min_rows": 21,
            "order": "Ascending by timeOpen is best; the API sorts if needed.",
            "target_modes": ["level", "delta", "logdiff"],
        },
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/model/info")
def model_info():
    return {
        "model_path": MODEL_PATH,
        "target_mode": MODEL_TARGET_MODE,
        "final_features": FINAL_FEATURES,
        "model_repr": str(model)[:400],
    }

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def _prepare_features(df_in: pd.DataFrame) -> pd.DataFrame:
    df_feat = build_features_from_ohlcv(df_in)
    df_feat = df_feat.dropna(subset=FINAL_FEATURES).reset_index(drop=True)
    return df_feat[FINAL_FEATURES]


def _invert_prediction(yhat_raw: float, last_high: Optional[float], mode: Literal["level", "delta", "logdiff"]) -> float:
    if mode == "level":
        return float(yhat_raw)
    if last_high is None or not np.isfinite(last_high):
        raise HTTPException(status_code=400, detail="Cannot invert prediction without a valid last high.")
    if mode == "delta":
        return float(last_high + yhat_raw)
    if mode == "logdiff":
        return float(np.exp(yhat_raw) * last_high)
    raise HTTPException(status_code=400, detail=f"Unknown target mode: {mode}")


def _to_utc(s: pd.Series) -> pd.Series:
    """Make a datetime Series uniformly UTC-aware."""
    s = pd.to_datetime(s, errors="coerce")
    # if tz-naive → localize to UTC; if tz-aware → convert to UTC
    return s.dt.tz_localize("UTC") if s.dt.tz is None else s.dt.tz_convert("UTC")

# --------------------------------------------------------------------------------------
# POST /predict  (user supplies candles)
# --------------------------------------------------------------------------------------
@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    mode = (req.target_mode or MODEL_TARGET_MODE).lower()  # type: ignore

    if not req.candles or len(req.candles) < 21:
        raise HTTPException(status_code=400, detail="Please provide at least 21 recent candles for features like volume_sma21.")

    df = pd.DataFrame([c.dict() for c in req.candles])
    missing_cols = {"timeOpen", "open", "high", "low", "close"} - set(df.columns)
    if missing_cols:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {sorted(missing_cols)}")

    # Force UTC-awareness and sort
    df = ensure_time_and_sort(df, time_col="timeOpen")  # your util should already do utc=True

    last_high = float(df["high"].iloc[-1])
    X = _prepare_features(df)
    if X.empty:
        raise HTTPException(status_code=400, detail="Not enough history after feature engineering (NaNs after lags/SMAs).")

    x_tail = X.iloc[[-1]]
    try:
        yhat_raw = float(model.predict(x_tail)[0])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model prediction failed: {e}")

    yhat = _invert_prediction(yhat_raw, last_high, mode)

    return PredictResponse(
        predicted_high_next_day=yhat,
        target_mode=mode,  # type: ignore
        last_known_high=last_high,
        features_used=FINAL_FEATURES,
        feature_vector_tail={k: (None if pd.isna(v) else float(v)) for k, v in x_tail.iloc[0].to_dict().items()},
    )

# --------------------------------------------------------------------------------------
# GET /predict/sol  (fetch candles for SOL* and predict)
# --------------------------------------------------------------------------------------
@app.get("/predict/sol", response_model=PredictTokenResponse)
def predict_sol(
    n: int = Query(64, ge=21, le=1000, description="History window size (must be >=21)"),
    target_mode: Optional[Literal["level", "delta", "logdiff"]] = Query(None),
):
    if fetch_candles is None:
        raise HTTPException(status_code=501, detail="No fetcher available. Ensure fetch/kraken_ohlc_solusd.py exists with get_recent_candles().")

    mode = (target_mode or MODEL_TARGET_MODE).lower()

    try:
        rows = fetch_candles("SOLUSD", n)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Fetcher failed: {e}")

    df = pd.DataFrame(rows)
    df = ensure_time_and_sort(df, time_col="timeOpen")

    if len(df) < 21:
        raise HTTPException(status_code=400, detail="Insufficient history (need >= 21 rows).")

    last_high = float(df["high"].iloc[-1])
    X = _prepare_features(df)
    if X.empty:
        raise HTTPException(status_code=400, detail="Not enough history after feature engineering (NaNs after lags/SMAs).")

    x_tail = X.iloc[[-1]]
    try:
        yhat_raw = float(model.predict(x_tail)[0])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model prediction failed: {e}")

    yhat = _invert_prediction(yhat_raw, last_high, mode)

    return PredictTokenResponse(
        token="SOLUSD",
        history_rows_used=len(df),
        predicted_high_next_day=yhat,
        target_mode=mode,  # type: ignore
        last_known_high=last_high,
        features_used=FINAL_FEATURES,
        feature_vector_tail={k: (None if pd.isna(v) else float(v)) for k, v in x_tail.iloc[0].to_dict().items()},
    )

# --------------------------------------------------------------------------------------
# GET /predict/sol/at  (anchor by date)
# --------------------------------------------------------------------------------------
@app.get("/predict/sol/at", response_model=PredictTokenResponse)
def predict_sol_at(
    date: str = Query(..., description="Anchor date/time in ISO format; we predict the next day from the last candle at/before this time."),
    n: int = Query(256, ge=21, le=2000, description="History window size to fetch."),
    target_mode: Optional[Literal["level", "delta", "logdiff"]] = Query(None),
):
    if fetch_candles is None:
        raise HTTPException(status_code=501, detail="No fetcher available. Ensure fetch/kraken_ohlc_solusd.py exists with get_recent_candles().")

    mode = (target_mode or MODEL_TARGET_MODE).lower()

    try:
        rows = fetch_candles("SOLUSD", n)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Fetcher failed: {e}")

    df = pd.DataFrame(rows)
    df = ensure_time_and_sort(df, time_col="timeOpen")

    # Cut to anchor — make *both* sides UTC-aware to avoid tz-naive/aware mismatch
    try:
        anchor = pd.to_datetime(date, utc=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date. Use ISO date or datetime, e.g., 2025-09-30 or 2025-09-30T00:00:00Z.")

    ts = pd.to_datetime(df["timeOpen"], utc=True)
    mask = ts <= anchor
    if not bool(mask.any()):
        raise HTTPException(status_code=404, detail="No candles at or before the requested date.")

    df_cut = df.loc[mask].copy()
    if len(df_cut) < 21:
        raise HTTPException(status_code=400, detail="Insufficient history before the requested date (need >= 21 rows).")

    last_high = float(df_cut["high"].iloc[-1])
    X = _prepare_features(df_cut)
    if X.empty:
        raise HTTPException(status_code=400, detail="Not enough history after feature engineering (NaNs after lags/SMAs).")

    x_tail = X.iloc[[-1]]
    try:
        yhat_raw = float(model.predict(x_tail)[0])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model prediction failed: {e}")

    yhat = _invert_prediction(yhat_raw, last_high, mode)

    return PredictTokenResponse(
        token="SOLUSD",
        history_rows_used=len(df_cut),
        predicted_high_next_day=yhat,
        target_mode=mode,  # type: ignore
        last_known_high=last_high,
        features_used=FINAL_FEATURES,
        feature_vector_tail={k: (None if pd.isna(v) else float(v)) for k, v in x_tail.iloc[0].to_dict().items()},
    )
