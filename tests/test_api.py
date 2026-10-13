from pathlib import Path

import pytest
from synthetic import FakeProvider, random_walk

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from tradescan.api.app import create_app  # noqa: E402
from tradescan.config import Settings  # noqa: E402


@pytest.fixture
def watchlists(tmp_path: Path) -> Path:
    (tmp_path / "demo.txt").write_text("# benchmark: SPY\nAAA BBB CCC\n")
    return tmp_path


@pytest.fixture
def client(watchlists: Path) -> TestClient:
    frames = {name: random_walk(1500, seed=seed) for seed, name in enumerate(["AAA", "BBB", "CCC", "SPY"], start=1)}
    return TestClient(create_app(Settings(), FakeProvider(frames), watchlists))


def test_meta_endpoints(client):
    assert client.get("/api/health").json()["status"] == "ok"
    config = client.get("/api/config").json()
    assert config["account"]["equity"] == 100_000
    assert set(config["engines"]) == {"vectorized", "cerebro"}
    signals = client.get("/api/signals").json()
    assert len(signals) == 30 and {"name", "family", "direction", "weight", "description"} <= set(signals[0])
    assert client.get("/api/watchlists").json() == [{"name": "demo", "tickers": ["AAA", "BBB", "CCC"], "benchmark": "SPY"}]


def test_scan_returns_scored_hits_without_nan(client):
    body = {"watchlist": "demo", "fresh_bars": 10, "min_score": -10, "account": {"equity": 50_000, "risk_pct": 0.5}}
    response = client.post("/api/scan", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["universe"] == "demo" and data["regime"]["benchmark"] == "SPY"
    assert data["hits"], "synthetic data should produce setups"
    hit = data["hits"][0]
    assert {"ticker", "direction", "fired", "score", "risk", "edge"} <= set(hit)
    assert hit["risk"]["risk_amount"] <= 50_000 * 0.005 + 1e-6
    scores = [item["score"]["total"] for item in data["hits"]]
    assert scores == sorted(scores, reverse=True)


def test_scan_filters_and_validation(client):
    long_only = client.post("/api/scan", json={"tickers": ["AAA"], "direction": "long", "min_score": -10, "fresh_bars": 20})
    assert {hit["direction"] for hit in long_only.json()["hits"]} <= {"long"}
    assert client.post("/api/scan", json={}).status_code == 422
    assert client.post("/api/scan", json={"watchlist": "demo", "tickers": ["AAA"]}).status_code == 422
    assert client.post("/api/scan", json={"watchlist": "nope"}).status_code == 404
    assert client.post("/api/scan", json={"watchlist": "../demo"}).status_code == 404
    assert client.post("/api/scan", json={"tickers": ["AAA"], "signals": ["bogus"]}).status_code == 400


def test_market_and_edge(client):
    market = client.post("/api/market", json={"watchlist": "demo"}).json()
    assert market["regime"]["universe_size"] == 3
    edge = client.post("/api/edge", json={"watchlist": "demo", "families": ["breakout"], "horizons": [5, 10]})
    assert edge.status_code == 200, edge.text
    data = edge.json()
    assert data["horizons"] == [5, 10] and data["tickers"] == 3
    assert {row["family"] for row in data["rows"]} == {"breakout"}
    assert all(len(row["stats"]) == 2 for row in data["rows"])
    assert client.post("/api/edge", json={"watchlist": "demo", "horizons": [0]}).status_code == 400


def test_backtest_and_chart(client):
    pytest.importorskip("backtrader")
    response = client.post(
        "/api/backtest", json={"ticker": "aaa", "signal": "donchian_breakout", "engines": ["vectorized", "cerebro"]}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ticker"] == "AAA" and len(data["runs"]) == 2
    vectorized, cerebro = data["runs"]
    assert vectorized["metrics"]["trades"] == cerebro["metrics"]["trades"] > 0
    assert len(vectorized["equity"]) == len(data["buy_hold"]) == 1500
    assert client.post("/api/backtest", json={"ticker": "AAA", "signal": "nope"}).status_code == 400
    assert client.post("/api/backtest", json={"ticker": "ZZZ", "signal": "golden_cross"}).status_code == 400
    assert client.post("/api/backtest", json={"ticker": "AAA", "signal": "golden_cross", "engines": ["x"]}).status_code == 400

    chart = client.get("/api/chart/AAA", params=[("signals", "golden_cross"), ("signals", "death_cross")]).json()
    assert len(chart["candles"]) == 1500
    assert len(chart["sma_slow"]) == 1500 - 199
    assert {event["signal"] for event in chart["events"]} <= {"golden_cross", "death_cross"}
    times = [event["time"] for event in chart["events"]]
    assert times == sorted(times)


def test_static_ui_with_spa_fallback(watchlists, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>ui</html>")
    (dist / "app.js").write_text("export {};")
    client = TestClient(create_app(Settings(), FakeProvider({}), watchlists, static_dir=dist))
    assert client.get("/").text == "<html>ui</html>"
    assert client.get("/app.js").headers["content-type"].startswith("text/javascript")
    assert client.get("/backtest").text == "<html>ui</html>"
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/missing").status_code == 404
