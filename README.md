# Solana Detail Page — Streamlit + FastAPI (Drop-in)

A focused Streamlit page that displays **Solana (SOL)** next-day high prediction, current metrics, interactive OHLCV history, and a filterable table — powered by your **FastAPI** backend.

> Display timezone: **Australia/Sydney** (backend should return UTC ISO timestamps; the page localizes for display).

---

## ✅ What you get

- **KPIs**
  - Next-day High Prediction (Δ vs last known high)
  - Current Price
  - Market Cap
- **History**
  - Date-range selector → loads OHLCV
  - Candlestick chart + SMA(7/21)
- **Drilldown**
  - Single-day OHLC snapshot (open/high/low/close/volume)
- **Model context**
  - `features_used` and latest `feature_vector_tail`
- **Data table (optional)**
  - Filterable by Close range and minimum Volume

---

## Drop-in Usage

1) **Place the page file**

Create `pages/solana_detail.py` and paste the page code you already have from me (`solana_detail_page()` implementation).  
_(Keep `st.set_page_config(...)` **only** in your app’s main entry, e.g. `app/main.py`.)_

2) **Repo layout**

```
.
├── app/
│   └── main.py                     # Streamlit entry (call st.set_page_config HERE only)
├── pages/
│   └── solana_detail.py            # contains solana_detail_page()
├── backend/
│   └── main.py                     # FastAPI app with /predict, /current, /ohlcv
├── requirements.txt                # Streamlit client deps
└── .streamlit/
    └── secrets.toml                # API base config
```

3) **Configure API base URL**

Create `.streamlit/secrets.toml`:

```toml
[api]
base_url = "http://localhost:8000"
```

You can override this at runtime in the page’s **Connection settings** expander.

---

## Backend API Contracts (FastAPI)

Adjust names/paths to your backend. The Streamlit page expects:

### 1) Prediction
```
GET /predict/{token}
```

**Example response (matches your payload):**
```json
{
  "predicted_high_next_day": 215.908464108939,
  "target_mode": "level",
  "last_known_high": 213.79,
  "features_used": [
    "close","open","low","close_ema3","low_ema3",
    "open_sma3","open_sma7","high_lag1","high_lag2",
    "low_lag1","low_lag2","close_lag3","volume",
    "volume_sma21","month"
  ],
  "feature_vector_tail": {
    "close": 208.73,
    "open": 213.02,
    "low": 204.28,
    "close_ema3": 209.510894253838,
    "low_ema3": 202.864570110406,
    "open_sma3": 209.15,
    "open_sma7": 207.212857142857,
    "high_lag1": 214.79,
    "high_lag2": 210.95,
    "low_lag1": 204.73,
    "low_lag2": 198.13,
    "close_lag3": 203.54,
    "volume": 314867.93870918,
    "volume_sma21": 354688.109098109,
    "month": 9
  },
  "token": "SOLUSD",
  "history_rows_used": 227
}
```

### 2) Current metrics (recommended)
```
GET /current/{token}
```
**Response:**
```json
{"current_price": 213.12, "market_cap": 9834567890.12}
```
> If you don’t have this endpoint, the page will **fallback** to `last_known_high` as the “current price”.

### 3) OHLCV
```
GET /ohlcv/{token}?start=YYYY-MM-DD&end=YYYY-MM-DD
```
**Response (list):**
```json
[
  {"time": "2025-09-01T00:00:00Z", "open": 210.1, "high": 214.8, "low": 204.3, "close": 208.7, "volume": 314867.9},
  ...
]
```
> **Return `time` in UTC** (with `Z`). The Streamlit page converts to **Australia/Sydney**.

---

## Quickstart

### 0) Python environment

**Conda (recommended):**
```bash
conda create -n solapp python=3.11.4 -y
conda activate solapp
```

**venv:**
```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

> **Do not** put `Python==3.11.4` in `requirements.txt`. Pip installs packages, not Python itself.

### 1) Install frontend deps

```bash
pip install streamlit requests plotly pandas python-dateutil pytz
```

### 2) Install backend deps (example)

```bash
pip install fastapi uvicorn[standard] pydantic pandas numpy joblib lightgbm
```

### 3) Run backend

```bash
# from backend/
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Smoke tests:**
```bash
curl http://localhost:8000/predict/SOLUSD
curl "http://localhost:8000/ohlcv/SOLUSD?start=2025-08-01&end=2025-10-29"
curl http://localhost:8000/current/SOLUSD
```





## Roadmap

- Residuals & prediction band in the table  
- Export CSV for selected range  
- Toggles for more indicators (EMA, ATR, returns/log-returns)  
- Confidence intervals if model provides them  
- Backend health checks surfaced on page

---

