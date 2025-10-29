# tests/test_kraken_integration.py
import json
import os
import pytest

from fetch.kraken_ohlc_solusd import request

@pytest.mark.skipif(
    not os.environ.get("KRAKEN_INTEGRATION"),
    reason="Set KRAKEN_INTEGRATION=1 to run live tests",
)
def test_live_ohlc_solusd_returns_expected_keys():
    resp = request(
        method="GET",
        path="/0/public/OHLC",
        query={"pair": "SOLUSD", "interval": 5},
        environment="https://api.kraken.com",
    )
    body = resp.read().decode()
    data = json.loads(body)

    assert "error" in data
    assert data["error"] == []  # Kraken returns [] on success

    assert "result" in data
    result = data["result"]
    assert "SOLUSD" in result
    # result["SOLUSD"] should be a list of OHLC rows
    assert isinstance(result["SOLUSD"], list)
    # Optional: check at least one row and its length (Kraken OHLC typically has 8 fields)
    if result["SOLUSD"]:
        assert len(result["SOLUSD"][0]) >= 6  # ts, o, h, l, c, v, ...
