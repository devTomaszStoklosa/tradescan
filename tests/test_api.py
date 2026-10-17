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
    assert set(sections) == {"account", "risk", "scan", "scoring", "trend", "regime", "backtest", "monte_carlo", "portfolio"}
    assert [name for name in sections["monte_carlo"]] == ["simulations", "ruin_drawdown_pct", "seed"]
    assert [name for name in sections["portfolio"]] == ["max_positions", "max_exposure_pct"]
    assert sections["account"]["equity"]["default"] == 100_000
    assert sections["risk"]["targets_r"] | {"kind": "float_list", "default": [2.0, 3.0]} == sections["risk"]["targets_r"]
    assert sections["scoring"]["family_weights"]["keys"] == ["trend", "momentum", "breakout", "mean_reversion", "volume", "pattern"]
    assert "cache_dir" not in str(config["sections"])
    assert set(config["engines"]) == {"vectorized", "cerebro"}
    assert [rule["name"] for rule in config["entry_rules"]] == ["next_open", "stop", "limit"]
    assert [rule["name"] for rule in config["exit_rules"]] == [
        "target", "time", "trailing", "channel", "breakeven", "rsi", "sma_revert", "sma_trend", "supertrend",
        "failed_breakout", "no_progress",
    ]
    assert (config["default_entry"], config["default_exits"]) == ("next_open", ["target", "time"])
    assert [(rule["name"], rule["needs_benchmark"]) for rule in config["filter_rules"]] == [
        ("trend", False), ("market", True), ("adx", False), ("volume", False), ("atr_pct", False),
    ]  # fmt: skip
    assert config["filter_rules"][0]["description"] == "Close above SMA(200) for longs, below it for shorts"
    limit = config["entry_rules"][2]
    assert [param["name"] for param in limit["params"]] == ["offset_atr", "valid_bars"]
    assert limit["description"].startswith("Buy-limit 0.5 ATR") and "{offset_atr:g}" in limit["template"]
    assert "target_r" not in str(config["sections"])
    assert [(rule["name"], rule["needs_scan"]) for rule in config["priority_rules"]] == [
        ("relative_strength", False), ("momentum", False), ("score", True),
    ]  # fmt: skip
    assert config["priority_rules"][2]["params"] == []
    assert config["default_priority"] == "relative_strength"
    momentum = config["priority_rules"][1]
    assert [param["name"] for param in momentum["params"]] == ["lookback", "skip"]
    assert momentum["description"] == "Return from 252 bars ago to 21 bars ago"

    signals = client.get("/api/signals").json()
    assert len(signals) == 38 and {"name", "family", "direction", "weight", "description", "template", "params"} <= set(signals[0])
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
        ("/api/backtest", {"ticker": "AAA", "signal": "golden_cross", "settings": {"monte_carlo": {"simulations": 50}}}),
        ("/api/backtest", {"ticker": "AAA", "signal": "golden_cross", "settings": {"monte_carlo": {"seed": 1.5}}}),
        ("/api/backtest", {"ticker": "AAA", "signal": "golden_cross", "entry": {"name": "nope"}}),
        ("/api/backtest", {"ticker": "AAA", "signal": "golden_cross", "entry": {"name": "limit", "params": {"valid_bars": 0}}}),
        ("/api/backtest", {"ticker": "AAA", "signal": "golden_cross", "exits": [{"name": "nope"}]}),
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


def test_backtest_with_moving_stops(client):
    body = {"ticker": "AAA", "signal": "connors_rsi2_long"}
    exits = [{"name": "trailing", "params": {"atr_mult": 1.5}}, {"name": "breakeven", "params": {"trigger_r": 2, "lock_r": 0.5}}]
    response = client.post("/api/backtest", json={**body, "exits": exits})
    assert response.status_code == 200, response.text
    data = response.json()
    assert [rule["description"] for rule in data["exits"]] == [
        "Stop 1.5 ATR below the highest high since the entry bar (above the lowest low for shorts), only tightening",
        "Once the gain reaches 2R from the fill, stop at 0.5R from the fill",
    ]
    reasons = {trade["exit_reason"] for trade in data["runs"][0]["trades"]}
    assert "trailing" in reasons and reasons <= {"stop", "trailing", "breakeven", "open"}

    invalid = client.post("/api/backtest", json={**body, "exits": [{"name": "breakeven", "params": {"lock_r": 1}}]})
    assert invalid.status_code == 400 and "must be below the trigger" in invalid.text


def test_backtest_with_indicator_exits(client):
    exits = [{"name": "rsi", "params": {"period": 3, "level": 65}}, {"name": "sma_trend", "params": {"period": 20}}]
    response = client.post("/api/backtest", json={"ticker": "AAA", "signal": "connors_rsi2_long", "exits": exits})
    assert response.status_code == 200, response.text
    data = response.json()
    assert [rule["description"] for rule in data["exits"]] == [
        "Exit at the next open once RSI(3) closes at or above 65 (at or below 100 minus that for shorts)",
        "Exit at the next open once the close is below SMA(20) (above it for shorts)",
    ]
    reasons = {trade["exit_reason"] for trade in data["runs"][0]["trades"]}
    assert "rsi" in reasons and reasons <= {"stop", "rsi", "sma_trend", "open"}


def test_backtest_with_entry_filters(client):
    body = {"ticker": "AAA", "signal": "connors_rsi2_long"}
    default = client.post("/api/backtest", json=body).json()
    assert default["filters"] == [] and default["benchmark"] is None

    filters = [{"name": "market", "params": {"period": 100}}, {"name": "volume", "params": {"min_ratio": 1.2}}]
    response = client.post("/api/backtest", json={**body, "filters": filters})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["benchmark"] == "SPY"
    assert [(rule["name"], rule["params"]) for rule in data["filters"]] == [
        ("market", {"period": 100}), ("volume", {"period": 20, "min_ratio": 1.2}),
    ]  # fmt: skip
    assert data["filters"][0]["description"] == "Benchmark close above its SMA(100) for longs, below it for shorts"
    assert 0 < len(data["runs"][0]["trades"]) < len(default["runs"][0]["trades"])

    def status(**extra):
        return client.post("/api/backtest", json={**body, **extra}).status_code

    assert status(filters=[{"name": "trend"}], benchmark="BBB") == 200
    assert status(filters=[{"name": "market"}], benchmark="NOPE") == 400
    assert status(filters=[{"name": "atr_pct", "params": {"min_pct": 6}}]) == 400  # above the default maximum
    assert status(filters=[{"name": "nope"}]) == 400
    assert status(filters=[{"name": "trend"}, {"name": "trend"}]) == 400

    axes = [{"target": "filter", "owner": "market", "name": "period", "values": [100, 200]}]
    sweep = client.post("/api/sweep", json={**body, "filters": filters, "axes": axes}).json()
    assert sweep["axes"][0]["key"] == "filter.market.period" and sweep["benchmark"] == "SPY"
    assert all(cell["error"] is None for cell in sweep["cells"])


def test_backtest_reports_the_split(client):
    body = {"ticker": "AAA", "signal": "connors_rsi2_long", "settings": {"backtest": {"oos_pct": 20}}}
    data = client.post("/api/backtest", json=body).json()
    assert data["config"]["oos_pct"] == 20
    split = data["split"]
    assert split["oos_pct"] == 20 and split["in_sample_start"] == data["start"] and split["out_of_sample_end"] == data["end"]
    assert split["in_sample_end"] < split["out_of_sample_start"]
    run = data["runs"][0]
    assert run["in_sample"]["trades"] > 0 and run["out_of_sample"]["trades"] > 0
    assert client.post("/api/backtest", json={**body, "settings": {"backtest": {"oos_pct": 60}}}).status_code == 400


def test_backtest_reports_the_monte_carlo(client):
    settings = {"monte_carlo": {"simulations": 200, "ruin_drawdown_pct": 20, "seed": 5}, "account": {"risk_pct": 2}}
    data = client.post("/api/backtest", json={"ticker": "AAA", "signal": "connors_rsi2_long", "settings": settings}).json()
    run = data["runs"][0]
    result = run["monte_carlo"]
    assert (result["simulations"], result["ruin_drawdown_pct"], result["seed"], result["risk_pct"]) == (200, 20, 5, 2)
    assert result["trades"] == run["metrics"]["trades"] > 1
    assert {"final_return_pct", "max_drawdown_pct", "longest_losing_streak"} == set(result["actual"])
    shuffled, bootstrapped = result["methods"]
    assert (shuffled["name"], bootstrapped["name"]) == ("shuffled", "bootstrapped")
    assert set(bootstrapped["final_return_pct"]) == {"p5", "p25", "p50", "p75", "p95"}
    assert bootstrapped["final_return_pct"]["p5"] <= bootstrapped["final_return_pct"]["p95"]
    assert 0 <= bootstrapped["ruin_pct"] <= 100


def test_sweep(client):
    axes = [
        {"target": "signal", "name": "oversold", "values": [10, 20]},
        {"target": "exit", "owner": "target", "name": "target_r", "values": [1.5, 2, 3]},
    ]
    response = client.post("/api/sweep", json={"ticker": "aaa", "signal": "connors_rsi2_long", "axes": axes})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ticker"] == "AAA" and data["engine"] == "vectorized" and data["split"]["oos_pct"] == 30
    first, second = data["axes"]
    assert (first["key"], first["label"], first["kind"], first["current"], first["values"]) == (
        "signal.oversold", "Oversold level", "float", 10, [10, 20]
    )  # fmt: skip
    assert (second["key"], second["owner"], second["unit"]) == ("exit.target.target_r", "target", "R")
    assert [cell["values"] for cell in data["cells"]] == [[10, 1.5], [10, 2], [10, 3], [20, 1.5], [20, 2], [20, 3]]
    assert all(cell["in_sample"]["trades"] > 0 and cell["out_of_sample"] and cell["error"] is None for cell in data["cells"])

    # A cell is the backtest of its combination, out-of-sample metrics included.
    body = {"ticker": "AAA", "signal": "connors_rsi2_long", "params": {"oversold": 20}, "exits": [{"name": "target"}, {"name": "time"}]}
    single = client.post("/api/backtest", json=body).json()["runs"][0]
    assert data["cells"][4]["out_of_sample"] == single["out_of_sample"]
    assert data["cells"][4]["in_sample"] == single["in_sample"]


def test_watchlist_backtest(client):
    setup = {"signal": "connors_rsi2_long", "filters": [{"name": "market"}]}
    response = client.post("/api/watchlist-backtest", json={"watchlist": "demo", **setup})
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["universe"], data["engine"], data["benchmark"], data["missing"]) == ("demo", "vectorized", "SPY", [])
    assert [row["ticker"] for row in data["rows"]] == ["AAA", "BBB", "CCC"]
    assert data["filters"][0]["name"] == "market" and "ticker" not in data

    # A row is the backtest of that ticker alone.
    single = client.post("/api/backtest", json={**setup, "ticker": "BBB", "benchmark": "SPY"}).json()
    row = data["rows"][1]
    assert row["metrics"] == single["runs"][0]["metrics"] and row["out_of_sample"] == single["runs"][0]["out_of_sample"]
    assert row["split"] == single["split"] and (row["start"], row["end"]) == (single["start"], single["end"])

    periods = {period["period"]: period for period in data["periods"]}
    assert list(periods) == ["full", "in_sample", "out_of_sample"]
    full = periods["full"]
    assert full["tickers"] == 3 and full["pooled"]["trades"] == sum(row["metrics"]["trades"] for row in data["rows"])
    spread = {item["metric"]: item for item in full["spread"]}
    assert len(spread) == 12 and spread["trades"]["above_break_even_pct"] is None
    assert spread["expectancy_r"]["minimum"] <= spread["expectancy_r"]["median"] <= spread["expectancy_r"]["maximum"]

    tickers = client.post("/api/watchlist-backtest", json={"tickers": ["aaa", "zzz"], "signal": "connors_rsi2_long"}).json()
    assert [row["ticker"] for row in tickers["rows"]] == ["AAA"] and tickers["missing"] == ["ZZZ"] and tickers["benchmark"] is None

    def status(**extra):
        return client.post("/api/watchlist-backtest", json={"signal": "connors_rsi2_long", **extra}).status_code

    assert status(watchlist="nope") == 404
    assert status(watchlist="demo", tickers=["AAA"]) == 422
    assert status(watchlist="demo", ticker="AAA") == 422  # the watchlist names the tickers
    assert status(tickers=["ZZZ"]) == 400
    assert status(watchlist="demo", filters=[{"name": "market"}], benchmark="NOPE") == 400
    assert client.post("/api/watchlist-backtest", json={"watchlist": "demo", "signal": "nope"}).status_code == 400


def test_portfolio_backtest(client):
    setup = {
        "signal": "connors_rsi2_long",
        "filters": [{"name": "market"}],
        "settings": {"portfolio": {"max_positions": 2, "max_exposure_pct": 60}},
        "priority": {"name": "momentum", "params": {"lookback": 126, "skip": 5}},
    }
    response = client.post("/api/portfolio-backtest", json={"watchlist": "demo", "engines": ["vectorized", "cerebro"], **setup})
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["universe"], data["benchmark"], data["buy_hold_benchmark"], data["missing"]) == ("demo", "SPY", "SPY", [])
    assert data["portfolio"] == {"max_positions": 2, "max_exposure_pct": 60.0}
    assert data["priority"]["name"] == "momentum" and data["priority"]["params"] == {"lookback": 126, "skip": 5}
    assert data["split"]["oos_pct"] == 30.0 and data["buy_hold"][0]["value"] == 100_000
    vectorized, cerebro = data["runs"]
    assert (vectorized["engine"], cerebro["engine"]) == ("vectorized", "cerebro")
    assert vectorized["full"]["metrics"] == pytest.approx(cerebro["full"]["metrics"], rel=1e-9)
    assert vectorized["full"]["stats"] == pytest.approx(cerebro["full"]["stats"], rel=1e-9)

    def keys(run):
        return [(trade["ticker"], trade["entry_date"], trade["exit_date"], trade["size"]) for trade in run["trades"]]

    assert keys(vectorized) == keys(cerebro)
    full = vectorized["full"]
    assert full["stats"]["max_positions"] <= 2 and full["metrics"]["trades"] > 0
    assert full["stats"]["orders"] >= full["metrics"]["trades"]
    assert {trade["ticker"] for trade in vectorized["trades"]} <= {"AAA", "BBB", "CCC"}
    assert [row["ticker"] for row in vectorized["tickers"]] == ["AAA", "BBB", "CCC"]
    assert sum(row["pnl"] for row in vectorized["tickers"]) == pytest.approx(vectorized["equity"][-1]["value"] - 100_000)
    assert len(vectorized["positions"]) == len(vectorized["equity"])
    assert vectorized["in_sample"]["metrics"]["trades"] > 0 and vectorized["out_of_sample"] is not None

    tickers = client.post("/api/portfolio-backtest", json={"tickers": ["aaa", "zzz"], "signal": "connors_rsi2_long"}).json()
    assert tickers["missing"] == ["ZZZ"] and tickers["benchmark"] is None and tickers["buy_hold_benchmark"] == "SPY"
    assert tickers["priority"]["name"] == "relative_strength" and [run["engine"] for run in tickers["runs"]] == ["vectorized"]

    def status(**extra):
        return client.post("/api/portfolio-backtest", json={"signal": "connors_rsi2_long", **extra}).status_code

    assert status(watchlist="nope") == 404
    assert status(watchlist="demo", ticker="AAA") == 422
    assert status(tickers=["ZZZ"]) == 400
    assert status(watchlist="demo", benchmark="NOPE") == 400  # buy & hold needs the benchmark
    assert status(watchlist="demo", engines=["nope"]) == 400
    assert status(watchlist="demo", priority={"name": "nope"}) == 400
    assert status(watchlist="demo", priority={"name": "momentum", "params": {"skip": 300}}) == 400
    assert status(watchlist="demo", settings={"portfolio": {"max_positions": 0}}) == 400


def test_portfolio_backtest_with_the_score_priority(client):
    def run(settings):
        body = {"watchlist": "demo", "signal": "connors_rsi2_long", "priority": {"name": "score"}, "settings": settings}
        return client.post("/api/portfolio-backtest", json={**body, "engines": ["vectorized", "cerebro"]})

    limits = {"portfolio": {"max_positions": 1}}
    response = run(limits)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["priority"] == {
        "name": "score",
        "label": "Scan score",
        "description": "The scanner's confluence score: fresh signals, daily and weekly trend, relative-strength rank",
        "params": {},
    }
    def keys(run):
        return [(trade["ticker"], trade["entry_date"], trade["exit_date"], trade["size"]) for trade in run["trades"]]

    vectorized, cerebro = data["runs"]
    assert keys(vectorized) == keys(cerebro) and vectorized["full"]["stats"]["skipped_no_slot"] > 0

    scoring = {"scoring": {"rs_bonus": 3, "family_weights": {"breakout": 0}}, "scan": {"fresh_bars": 1}, "trend": {"fast_period": 20}}
    assert run({**limits, **scoring}).status_code == 200
    assert run({"scoring": {"rs_strong_pct": 10}}).status_code == 400
    assert run({"scoring": {"signal_weights": {"nope": 1}}}).status_code == 400


def test_sweep_limits_and_errors(client):
    limits = client.get("/api/config").json()["sweep"]
    assert limits == {
        "max_axes": 2, "min_values": 2, "max_values": 50, "max_combinations": 200,
        "sections": ["account", "risk", "backtest"], "fixed": ["backtest.oos_pct"], "min_period_bars": 60,
    }  # fmt: skip

    def sweep(*axes, **extra):
        return client.post("/api/sweep", json={"ticker": "AAA", "signal": "golden_cross", "axes": list(axes), **extra})

    fast = {"target": "signal", "name": "fast", "values": list(range(150, 251, 50))}
    cells = sweep(fast).json()["cells"]
    assert [cell["error"] is None for cell in cells] == [True, False, False]
    assert sweep({**fast, "values": list(range(2, 17))}, {**fast, "name": "slow", "values": list(range(300, 314))}).status_code == 400
    assert sweep({**fast, "values": [1, 2]}).status_code == 400
    assert sweep({**fast, "values": [50]}).status_code == 422
    assert sweep({"target": "settings", "owner": "backtest", "name": "oos_pct", "values": [20, 30]}).status_code == 400
    assert sweep({"target": "settings", "owner": "monte_carlo", "name": "seed", "values": [1, 2]}).status_code == 400
    assert sweep({"target": "nope", "name": "fast", "values": [5, 6]}).status_code == 422
    assert sweep(fast, engines=["cerebro"]).status_code == 422  # engines belong to backtests
    assert client.post("/api/sweep", json={"ticker": "AAA", "signal": "nope", "axes": [fast]}).status_code == 400


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
