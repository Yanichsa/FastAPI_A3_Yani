# tests/test_kraken_unit.py
import io
import json
from types import SimpleNamespace
from unittest.mock import patch

from fetch.kraken_ohlc_solusd import request

class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._buf = io.BytesIO(json.dumps(payload).encode())
    def read(self) -> bytes:
        return self._buf.getvalue()

def _fake_success_payload():
    # Minimal realistic OHLC structure
    return {
        "error": [],
        "result": {
            "SOLUSD": [
                # [time, open, high, low, close, vwap, volume, count]
                [1710000000, "150.1", "151.0", "149.8", "150.6", "150.5", "123.45", 1000],
            ],
            "last": 1710000300,
        },
    }

@patch("urllib.request.urlopen")
def test_request_builds_url_and_parses_response(mock_urlopen):
    mock_urlopen.return_value = _FakeHTTPResponse(_fake_success_payload())

    resp = request(
        method="GET",
        path="/0/public/OHLC",
        query={"pair": "SOLUSD", "interval": 5},
        environment="https://api.kraken.com",
    )
    body = resp.read().decode()
    data = json.loads(body)

    assert data["error"] == []
    assert "result" in data and "SOLUSD" in data["result"]
    rows = data["result"]["SOLUSD"]
    assert isinstance(rows, list) and len(rows) == 1
