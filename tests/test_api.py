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
    sections = {section["name"]: {param["name"]: param for param in section["params"]} for section in config["sections"]}
    assert set(sections) == {"account", "risk", "scan", "scoring", "trend", "regime", "backtest"}
    assert sections["account"]["equity"]["default"] == 100_000
    assert sections["risk"]["targets_r"] | {"kind": "float_list", "default": [2.0, 3.0]} == sections["risk"]["targets_r"]
    assert sections["scoring"]["family_weights"]["keys"] == ["trend", "momentum", "breakout", "mean_reversion", "volume", "pattern"]
    assert "cache_dir" not in str(config["sections"])
    assert set(config["engines"]) == {"vectorized", "cerebro"}
    assert [rule["name"] for rule in config["entry_rules"]] == ["next_open", "stop", "limit"]
    assert [rule["name"] for rule in config["exit_rules"]] == ["target", "time"]
    assert (config["default_entry"], config["default_exits"]) == ("next_open", ["target", "time"])
    limit = config["entry_rules"][2]
    assert [param["name"] for param in limit["params"]] == ["offset_atr", "valid_bars"]
    assert limit["description"].startswith("Buy-limit 0.5 ATR") and "{offset_atr:g}" in limit["template"]
    assert "target_r" not in str(config["sections"])

    signals = client.get("/api/signals").json()
    assert len(signals) == 30 and {"name", "family", "direction", "weight", "description", "template", "params"} <= set(signals[0])
    rsi2 = next(signal for signal in signals if signal["name"] == "connors_rsi2_long")
    assert [param["name"] for param in rsi2["params"]] == ["rsi_period", "trend_period", "oversold"]
    assert rsi2["description"].startswith("RSI(2) < 10 while") and "{oversold:g}" in rsi2["template"]
    assert client.get("/api/watchlists").json() == [{"name": "demo", "tickers": ["AAA", "BBB", "CCC"], "benchmark": "SPY"}]


def test_scan_returns_scored_hits_without_nan(client):
    settings = {"scan": {"fresh_bars": 10, "min_score": -10}, "account": {"equity": 50_000, "risk_pct": 0.5}}
    response = client.post("/api/scan", json={"watchlist": "demo", "settings": settings})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["universe"] == "demo" and data["regime"]["benchmark"] == "SPY"
    assert data["hits"], "synthetic data should produce setups"
    hit = data["hits"][0]
    assert {"ticker", "direction", "fired", "score", "risk", "edge"} <= set(hit)
    assert hit["risk"]["risk_amount"] <= 50_000 * 0.005 + 1e-6
    scores = [item["score"]["total"] for item in data["hits"]]
    assert scores == sorted(scores, reverse=True)
    assert data["fresh_bars"] == 10 and data["min_score"] == -10


def test_scan_filters_and_validation(client):
    settings = {"scan": {"fresh_bars": 20, "min_score": -10}}
    long_only = client.post("/api/scan", json={"tickers": ["AAA"], "direction": "long", "settings": settings})
    assert {hit["direction"] for hit in long_only.json()["hits"]} <= {"long"}
    assert client.post("/api/scan", json={}).status_code == 422
    assert client.post("/api/scan", json={"watchlist": "demo", "tickers": ["AAA"]}).status_code == 422
    assert client.post("/api/scan", json={"watchlist": "nope"}).status_code == 404
    assert client.post("/api/scan", json={"watchlist": "../demo"}).status_code == 404
    assert client.post("/api/scan", json={"tickers": ["AAA"], "signals": ["bogus"]}).status_code == 400
    # Removed one-off fields are rejected rather than silently ignored; paths never parse as parameters.
    assert client.post("/api/scan", json={"tickers": ["AAA"], "min_score": 1}).status_code == 422
    assert client.post("/api/scan", json={"tickers": ["AAA"], "settings": {"data": {"cache_dir": "C:/"}}}).status_code == 422


def test_scan_reports_the_weights_this_run_used(client):
    settings = {"scan": {"fresh_bars": 30, "min_score": -10}, "scoring": {"family_weights": {"breakout": 4}}}
    hits = client.post("/api/scan", json={"watchlist": "demo", "families": ["breakout"], "settings": settings}).json()["hits"]
    assert hits and {item["weight"] for hit in hits for item in hit["fired"]} == {4}


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


def test_signal_parameters_change_results(client):
    base = {"watchlist": "demo", "signals": ["connors_rsi2_long"], "horizons": [5]}
    default = client.post("/api/edge", json=base).json()["rows"][0]
    looser = client.post("/api/edge", json={**base, "signal_params": {"connors_rsi2_long": {"oversold": 30}}}).json()["rows"][0]
    assert looser["stats"][0]["events"] > default["stats"][0]["events"]
    assert looser["description"].startswith("RSI(2) < 30 while")


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/edge", {"watchlist": "demo", "signal_params": {"connors_rsi2_long": {"oversold": 500}}}),
        ("/api/edge", {"watchlist": "demo", "signal_params": {"connors_rsi2_long": {"overbought": 90}}}),
        ("/api/edge", {"watchlist": "demo", "signal_params": {"nope": {"period": 1}}}),
        ("/api/scan", {"watchlist": "demo", "settings": {"data": {"cache_ttl_hours": 0}}}),
        ("/api/scan", {"watchlist": "demo", "settings": {"risk": {"atr_mult": -1}}}),
        ("/api/scan", {"watchlist": "demo", "settings": {"risk": {"atr_period": 2.5}}}),
        ("/api/scan", {"watchlist": "demo", "settings": {"scoring": {"signal_weights": {"nope": 1}}}}),
        ("/api/scan", {"watchlist": "demo", "settings": {"scoring": {"family_weights": {"nope": 1}}}}),
        ("/api/scan", {"watchlist": "demo", "settings": {"trend": {"rs_weights": [1.0]}}}),
        ("/api/market", {"watchlist": "demo", "settings": {"regime": {"risk_off_breadth": 70}}}),
        ("/api/backtest", {"ticker": "AAA", "signal": "golden_cross", "params": {"fast": 300}}),
        ("/api/backtest", {"ticker": "AAA", "signal": "golden_cross", "settings": {"backtest": {"period": 5}}}),
        ("/api/backtest", {"ticker": "AAA", "signal": "golden_cross", "settings": {"backtest": {"target_r": 3}}}),
        ("/api/backtest", {"ticker": "AAA", "signal": "golden_cross", "entry": {"name": "nope"}}),
        ("/api/backtest", {"ticker": "AAA", "signal": "golden_cross", "entry": {"name": "limit", "params": {"valid_bars": 0}}}),
        ("/api/backtest", {"ticker": "AAA", "signal": "golden_cross", "exits": [{"name": "trailing"}]}),
        ("/api/backtest", {"ticker": "AAA", "signal": "golden_cross", "exits": [{"name": "time"}, {"name": "time"}]}),
        ("/api/backtest", {"ticker": "AAA", "signal": "golden_cross", "exits": [{"name": "target", "params": {"max_hold_bars": 5}}]}),
        ("/api/chart", {"ticker": "AAA", "signals": ["golden_cross"], "signal_params": {"golden_cross": {"slow": 1}}}),
    ],
)
def test_invalid_overrides_are_rejected(client, path, body):
    response = client.post(path, json=body)
    assert response.status_code == 400, response.text


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

    chart = client.post("/api/chart", json={"ticker": "AAA", "signals": ["golden_cross", "death_cross"]}).json()
    assert len(chart["candles"]) == 1500
    assert len(chart["sma_slow"]) == 1500 - 199
    assert {event["signal"] for event in chart["events"]} <= {"golden_cross", "death_cross"}
    times = [event["time"] for event in chart["events"]]
    assert times == sorted(times)


def test_backtest_and_chart_use_the_given_parameters(client):
    settings = {"risk": {"atr_mult": 3}, "account": {"max_position_pct": 50}}
    exits = [{"name": "time", "params": {"max_hold_bars": 7}}]
    body = {"ticker": "AAA", "signal": "donchian_breakout", "params": {"period": 40}, "settings": settings, "exits": exits}
    data = client.post("/api/backtest", json=body).json()
    assert data["params"] == {"period": 40} and "previous 40 bars" in data["description"]
    config = data["config"]
    assert (config["atr_mult"], config["max_position_pct"]) == (3, 50)
    assert data["entry"] == {
        "name": "next_open",
        "label": "Next open",
        "description": "Market order at the next open; stop and target are measured from the signal bar's close",
        "params": {},
    }
    assert [(rule["name"], rule["params"]) for rule in data["exits"]] == [("time", {"max_hold_bars": 7})]
    reasons = {trade["exit_reason"] for trade in data["runs"][0]["trades"]}
    assert "target" not in reasons and "time" in reasons

    def events(params):
        body = {"ticker": "AAA", "signals": ["donchian_breakout"], "signal_params": {"donchian_breakout": params}}
        return client.post("/api/chart", json=body).json()["events"]

    assert 0 < len(events({"period": 60})) < len(events({}))


def test_backtest_entry_and_exit_rules(client):
    body = {"ticker": "AAA", "signal": "connors_rsi2_long"}
    default = client.post("/api/backtest", json=body).json()
    assert [rule["name"] for rule in default["exits"]] == ["target", "time"]
    assert default["exits"][0]["description"] == "Limit order 2R from the entry reference"

    entry = {"name": "limit", "params": {"offset_atr": 1, "valid_bars": 3}}
    limit = client.post("/api/backtest", json={**body, "entry": entry, "exits": []}).json()
    assert limit["entry"]["params"] == {"offset_atr": 1.0, "valid_bars": 3}
    assert limit["entry"]["description"].startswith("Buy-limit 1 ATR below") and limit["exits"] == []
    trades = limit["runs"][0]["trades"]
    assert trades and {trade["exit_reason"] for trade in trades} <= {"stop", "open"}
    assert all(trade["entry_date"] > trade["signal_date"] for trade in trades)
    assert [trade["entry_date"] for trade in trades] != [trade["entry_date"] for trade in default["runs"][0]["trades"]]


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
