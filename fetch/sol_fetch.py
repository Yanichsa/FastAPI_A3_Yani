from __future__ import annotations

from typing import List, Dict
from datetime import datetime, timezone
import requests

# SOL-only public OHLC fetcher for Kraken
# Implements: get_recent_candles(token: str, n: int, interval: int = 1440) -> List[dict]
# token must be one of: SOL, SOLUSD, SOLUSDT (any case; dashes ignored)

_ALLOWED = {"SOL": "SOLUSD", "SOLUSD": "SOLUSD", "SOLUSDT": "SOLUSDT"}


def _norm_token(token: str) -> str:
    t = token.upper().replace("-", "")
    if t not in _ALLOWED:
        raise ValueError("Only Solana supported. Use SOL, SOLUSD or SOLUSDT.")
    return _ALLOWED[t]


def _iso(sec: int) -> str:
    return datetime.fromtimestamp(sec, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def get_recent_candles(token: str, n: int, interval: int = 1440) -> List[Dict]:
    pair = _norm_token(token)
    url = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": pair, "interval": interval}

    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    if data.get("error"):
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
        ts = int(row[0])
        out.append({
            "timeOpen": _iso(ts),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[6]),
        })

    out.sort(key=lambda d: d["timeOpen"])  # ascending
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(get_recent_candles("SOLUSD", n=5), indent=2))
