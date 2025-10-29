from __future__ import annotations

from typing import List, Dict, Optional
from datetime import datetime, timezone
import requests

# -----------------------------------------------------------------------------
# Kraken OHLC fetcher (public endpoint, no auth required)
# Implements the signature expected by app.main:
#   get_recent_candles(token: str, n: int, interval: int = 1440) -> List[dict]
# Returns list of dicts with keys: timeOpen, open, high, low, close, volume
# -----------------------------------------------------------------------------

_PAIR_ALIASES = {
    "SOL": "SOLUSD",
    "SOLUSD": "SOLUSD",
    "SOLUSDT": "SOLUSDT",
}



# Add near the top
_ALLOWED_INTERVALS = {1, 5, 15, 30, 60, 240, 1440, 10080}  # Kraken-supported mins

def get_recent_candles(token: str, n: int, interval: int = 1440) -> List[Dict]:
    if n <= 0:
        return []
    if interval not in _ALLOWED_INTERVALS:
        raise ValueError(f"Unsupported interval={interval}. Choose one of {_ALLOWED_INTERVALS}.")

    pair = _kraken_pair(token)
    url = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": pair, "interval": interval}

    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        raise RuntimeError(f"HTTP error contacting Kraken: {e}") from e
    except ValueError as e:
        raise RuntimeError(f"Invalid JSON from Kraken: {e}") from e

    if not isinstance(data, dict):
        raise RuntimeError("Unexpected Kraken response type")
    if data.get("error"):  # Kraken returns [] on success
        raise RuntimeError(f"Kraken error: {data['error']}")

    res = data.get("result", {})
    key = next((k for k in res.keys() if k.lower() == pair.lower()), None)
    if key is None:
        keys = [k for k in res.keys() if k != "last"]
        if not keys:
            raise RuntimeError(f"Unexpected Kraken payload keys: {list(res.keys())}")
        key = keys[0]

    rows = res.get(key, [])
    if not rows:
        raise RuntimeError("No OHLC rows returned from Kraken.")

    out: List[Dict] = []
    for row in rows[-n:]:
        try:
            ts = int(row[0])
            out.append({
                "timeOpen": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[6]),
            })
        except Exception:
            continue

    out.sort(key=lambda d: d["timeOpen"])
    return out


def _kraken_pair(token: str) -> str:
    t = token.upper().replace("-", "")
    # Restrict to SOL only
    if t not in _PAIR_ALIASES:
        raise ValueError("Only Solana is supported. Use SOL, SOLUSD or SOLUSDT.")
    return _PAIR_ALIASES[t]


def _iso_from_epoch(sec: int) -> str:
    return datetime.fromtimestamp(sec, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def get_recent_candles(token: str, n: int, interval: int = 1440) -> List[Dict]: # signature unchanged
    """Fetch last n OHLC candles for a token pair from Kraken.

    Args:
        token: market pair like "SOLUSD" (BTC is XBT on Kraken, alias handled).
        n: number of rows to return (most-recent last).
        interval: bar size in minutes (5 for 5-min, 60 for hourly, 1440 for daily).

    Returns:
        List of dicts with fields: timeOpen, open, high, low, close, volume.
    """
    if n <= 0:
        return []

    pair = _kraken_pair(token)
    url = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": pair, "interval": interval}

    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise RuntimeError(f"HTTP error contacting Kraken: {e}")

    if not isinstance(data, dict):
        raise RuntimeError("Unexpected Kraken response type")

    if data.get("error"):
        raise RuntimeError(f"Kraken error: {data['error']}")

    res = data.get("result", {})
    # Find the key that matches the requested pair (case-insensitive),
    # falling back to the first non-'last' key if Kraken changed case.
    key: Optional[str] = None
    for k in res.keys():
        if k.lower() == pair.lower():
            key = k
            break
    if key is None:
        keys = [k for k in res.keys() if k != "last"]
        if not keys:
            raise RuntimeError(f"Unexpected Kraken payload keys: {list(res.keys())}")
        key = keys[0]

    rows = res.get(key, [])
    if not rows:
        raise RuntimeError("No OHLC rows returned from Kraken.")

    # Each row format: [time, open, high, low, close, vwap, volume, count]
    out: List[Dict] = []
    for row in rows[-n:]:
        try:
            ts = int(row[0])
            out.append({
                "timeOpen": _iso_from_epoch(ts),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[6]),
            })
        except Exception:
            # skip malformed lines
            continue

    # Ensure ascending by time
    out.sort(key=lambda d: d["timeOpen"]) 
    return out


# Backward-compatible demo for quick CLI testing
if __name__ == "__main__":
    import sys, json as _json
    pair = sys.argv[1] if len(sys.argv) > 1 else "SOLUSD"
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    candles = get_recent_candles(pair, n=n, interval=interval)
    print(_json.dumps(candles, indent=2))
