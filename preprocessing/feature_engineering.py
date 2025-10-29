from __future__ import annotations

from typing import Optional, List
import numpy as np
import pandas as pd

# The exact feature order expected by the model
FINAL_FEATURES: List[str] = [
    "close", "open", "low",
    "close_ema3", "low_ema3",
    "open_sma3", "open_sma7",
    "high_lag1", "high_lag2",
    "low_lag1", "low_lag2",
    "close_lag3",
    "volume", "volume_sma21",
    "month",
]

__all__ = [
    "FINAL_FEATURES",
    "ensure_time_and_sort",
    "build_features_from_ohlcv",
]

# ----------------------- utils -----------------------

def ensure_time_and_sort(
    df: pd.DataFrame,
    time_col: str = "timeOpen",
    fallback_time_col: str = "time",
    group_by: Optional[str] = None,
) -> pd.DataFrame:
    """Ensure we have a proper datetime index and sorted order.
    Adds a 'month' column used by the feature list.
    """
    if time_col not in df.columns:
        if fallback_time_col in df.columns:
            df[time_col] = df[fallback_time_col]
        else:
            raise ValueError("No time column found. Provide 'timeOpen' or 'time'.")
    df[time_col] = pd.to_datetime(df[time_col])
    if group_by and group_by in df.columns:
        df = df.sort_values([group_by, time_col]).reset_index(drop=True)
    else:
        df = df.sort_values(time_col).reset_index(drop=True)
    df["month"] = df[time_col].dt.month
    return df


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=1).mean()


# ------------------ main feature builder ------------------

def build_features_from_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the features expected by the trained model.
    Expects columns: open, high, low, close, (optional) volume, and timeOpen/time.
    """
    if not {"open", "high", "low", "close"}.issubset(df.columns):
        missing = {"open", "high", "low", "close"} - set(df.columns)
        raise ValueError(f"Missing required OHLC columns: {sorted(missing)}")

    df = ensure_time_and_sort(df)

    # EMAs & SMAs
    df["close_ema3"] = _ema(df["close"], 3)
    df["low_ema3"] = _ema(df["low"], 3)
    df["open_sma3"] = _sma(df["open"], 3)
    df["open_sma7"] = _sma(df["open"], 7)

    # Volume SMA21 if present; else NaNs (model will drop rows missing FINAL_FEATURES)
    if "volume" in df.columns:
        df["volume_sma21"] = _sma(df["volume"], 21)
    else:
        df["volume_sma21"] = np.nan

    # Lags
    df["high_lag1"] = df["high"].shift(1)
    df["high_lag2"] = df["high"].shift(2)
    df["low_lag1"] = df["low"].shift(1)
    df["low_lag2"] = df["low"].shift(2)
    df["close_lag3"] = df["close"].shift(3)

    return df
