from pathlib import Path

import pytest
from synthetic import FakeProvider, random_walk

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from tradescan.api.app import create_app  # noqa: E402
from tradescan.config import Settings  # noqa: E402
from tradescan.storage.database import Database  # noqa: E402


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
    assert set(sections) == {
        "account", "risk", "scan", "scoring", "trend", "regime", "backtest", "pyramid", "monte_carlo", "portfolio",
        "rotation", "walk_forward",
    }  # fmt: skip
    assert [(name, spec["default"]) for name, spec in sections["walk_forward"].items()] == [
        ("windows", 5), ("in_sample_ratio", 3.0), ("min_trades", 10),
    ]  # fmt: skip
    assert [name for name in sections["rotation"]] == ["holdings", "absolute_lookback"]
    assert [(name, spec["default"]) for name, spec in sections["pyramid"].items()] == [("max_units", 1), ("add_every_atr", 0.5)]
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
    assert [rule["name"] for rule in config["ranking_rules"]] == ["relative_strength", "momentum"]
    assert [rule["name"] for rule in config["weight_rules"]] == ["equal", "inverse_volatility"]
    assert (config["default_ranking"], config["default_weighting"]) == ("momentum", "equal")
    assert config["rebalances"] == ["weekly", "monthly"]

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


def test_backtest_with_pyramiding(client):
    body = {"ticker": "AAA", "signal": "donchian_breakout", "engines": ["vectorized", "cerebro"]}
    default = client.post("/api/backtest", json=body).json()
    assert (default["config"]["max_units"], default["config"]["add_every_atr"]) == (1, 0.5)
    assert all(trade["adds"] == [] for run in default["runs"] for trade in run["trades"])

    settings = {"pyramid": {"max_units": 3, "add_every_atr": 1}}
    response = client.post("/api/backtest", json={**body, "settings": settings})
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["config"]["max_units"], data["config"]["add_every_atr"]) == (3, 1.0)
    vectorized, cerebro = (run["trades"] for run in data["runs"])
    pyramided = [trade for trade in vectorized if trade["adds"]]
    assert pyramided and all(len(trade["adds"]) <= 2 for trade in vectorized)
    assert all(trade["adds"][0]["date"] > trade["entry_date"] for trade in pyramided)
    assert [[fill["date"] for fill in trade["adds"]] for trade in vectorized] == [
        [fill["date"] for fill in trade["adds"]] for trade in cerebro
    ]
    assert client.post("/api/backtest", json={**body, "settings": {"pyramid": {"max_units": 0}}}).status_code == 400


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

    units = [{"target": "settings", "owner": "pyramid", "name": "max_units", "values": [1, 3]}]
    pyramid = client.post("/api/sweep", json={"ticker": "AAA", "signal": "donchian_breakout", "axes": units}).json()
    assert pyramid["axes"][0]["key"] == "settings.pyramid.max_units" and pyramid["axes"][0]["label"] == "Max units"
    first, third = (cell["in_sample"] for cell in pyramid["cells"])
    assert first["trades"] > 0 and first != third


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
    pyramided = client.post(
        "/api/portfolio-backtest", json={"signal": "connors_rsi2_long", "watchlist": "demo", "settings": {"pyramid": {"max_units": 2}}}
    )
    assert pyramided.status_code == 400 and "does not pyramid" in pyramided.json()["detail"]


def test_rotation_backtest(client):
    body = {
        "watchlist": "demo",
        "ranking": {"name": "momentum", "params": {"lookback": 126, "skip": 0}},
        "weighting": {"name": "inverse_volatility", "params": {"lookback": 20}},
        "rebalance": "weekly",
        "safe_asset": "spy",
        "settings": {"rotation": {"holdings": 2, "absolute_lookback": 63}, "backtest": {"commission_pct": 0.05}},
    }
    response = client.post("/api/rotation-backtest", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["universe"], data["engine"]) == ("demo", "vectorized")
    assert data["rotation"] == {"holdings": 2, "absolute_lookback": 63, "rebalance": "weekly", "safe_asset": "SPY"}
    assert data["ranking"]["params"] == {"lookback": 126, "skip": 0} and data["weighting"]["name"] == "inverse_volatility"
    assert data["config"]["commission_pct"] == 0.05
    assert data["buy_hold_benchmark"] == "SPY" and data["buy_hold"][0]["value"] == pytest.approx(100_000)
    assert data["start"] == data["equity"][0]["time"] == data["buy_hold"][0]["time"]
    assert data["split"] and data["in_sample"] and data["out_of_sample"]
    full = data["full"]
    assert full["metrics"]["expectancy_r"] is None and full["stats"]["rebalances"] > 50 and full["stats"]["max_holdings"] <= 3
    assert [row["ticker"] for row in data["tickers"]] == ["AAA", "BBB", "CCC", "SPY"]
    assert data["trades"] and all(trade["r_multiple"] is None for trade in data["trades"])
    targets = data["targets"]
    assert targets["date"] == data["end"] and len(targets["picks"]) == 2
    assert sum(pick["weight_pct"] for pick in targets["picks"]) == pytest.approx(100.0)


def test_rotation_backtest_rejects_what_it_cannot_run(client):
    def status(**extra):
        return client.post("/api/rotation-backtest", json={"watchlist": "demo", **extra}).status_code

    assert status() == 200
    assert status(ranking={"name": "score"}) == 400
    assert status(weighting={"name": "nope"}) == 400
    assert status(weighting={"name": "inverse_volatility", "params": {"lookback": 1}}) == 400
    assert status(rebalance="daily") == 422
    assert status(safe_asset="NOPE") == 400
    assert status(settings={"rotation": {"holdings": 0}}) == 400
    assert status(watchlist="nope") == 404


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


def test_portfolio_backtest_with_the_score_signal_params(client):
    def run(score_signal_params):
        body = {"watchlist": "demo", "signal": "connors_rsi2_long", "priority": {"name": "score"}}
        return client.post("/api/portfolio-backtest", json={**body, "score_signal_params": score_signal_params})

    assert run({"donchian_breakout": {"period": 5}, "connors_rsi2_long": {"oversold": 30}}).status_code == 200
    unknown = run({"nope": {"period": 5}})
    assert unknown.status_code == 400 and "nope" in unknown.json()["detail"]
    assert run({"donchian_breakout": {"period": 1}}).status_code == 400
    assert run({"donchian_breakout": {"nope": 5}}).status_code == 400


def test_sweep_limits_and_errors(client):
    limits = client.get("/api/config").json()["sweep"]
    assert limits == {
        "max_axes": 2, "min_values": 2, "max_values": 50, "max_combinations": 200,
        "sections": ["account", "risk", "backtest", "pyramid"], "fixed": ["backtest.oos_pct"], "min_period_bars": 60,
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


def test_walk_forward(client):
    axes = [
        {"target": "signal", "name": "oversold", "values": [5, 10, 15, 20]},
        {"target": "exit", "owner": "target", "name": "target_r", "values": [1.5, 2.5]},
    ]
    body = {"ticker": "aaa", "signal": "connors_rsi2_long", "axes": axes, "settings": {"walk_forward": {"min_trades": 5}}}
    response = client.post("/api/walk-forward", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["ticker"], data["engine"], data["scheme"], data["metric"]) == ("AAA", "vectorized", "rolling", "sharpe")
    assert data["walk_forward"] == {
        "windows": 5, "in_sample_ratio": 3, "min_trades": 5, "in_sample_bars": 561, "out_of_sample_bars": 187,
    }  # fmt: skip
    assert [axis["key"] for axis in data["axes"]] == ["signal.oversold", "exit.target.target_r"]
    assert data["combinations"] == 8 and data["errors"] == []
    windows = data["windows"]
    assert len(windows) == 5 and windows[0]["out_of_sample_start"] == data["out_of_sample_start"]
    assert windows[-1]["out_of_sample_end"] == data["end"] and windows[1]["in_sample_end"] < windows[1]["out_of_sample_start"]
    picked = [window for window in windows if window["values"] is not None]
    assert picked and all(len(window["values"]) == 2 and window["in_sample"]["trades"] >= 5 for window in picked)
    assert all(window["traded_from"] >= window["out_of_sample_start"] for window in windows if window["traded_from"])
    assert data["next"]["in_sample_end"] == data["end"] and data["next"]["qualified"] <= 8
    assert data["equity"][0]["time"] == data["out_of_sample_start"] and data["equity"][-1]["time"] == data["end"]
    assert len(data["equity"]) == len(data["unchanged_equity"]) == len(data["buy_hold"])
    assert data["metrics"]["trades"] == sum(window["out_of_sample"]["trades"] for window in windows if window["out_of_sample"])
    assert len(data["trades"]) >= data["metrics"]["trades"]
    assert data["metrics"]["buy_hold_pct"] == data["unchanged"]["buy_hold_pct"]

    anchored = client.post("/api/walk-forward", json={**body, "scheme": "anchored", "metric": "expectancy_r"}).json()
    assert anchored["scheme"] == "anchored"
    assert all(window["in_sample_start"] == anchored["start"] for window in anchored["windows"])


def test_walk_forward_limits_and_errors(client):
    limits = client.get("/api/config").json()["walk_forward"]
    assert limits["max_runs"] == 2000 and limits["schemes"] == ["rolling", "anchored"] and limits["default_scheme"] == "rolling"
    assert limits["default_metric"] == "sharpe" and "trades" not in limits["metrics"] and "expectancy_r" in limits["metrics"]
    assert limits["fixed"] == ["account.equity", "backtest.oos_pct"]

    def walk_forward(*axes, **extra):
        body = {"ticker": "AAA", "signal": "connors_rsi2_long", "axes": list(axes), **extra}
        return client.post("/api/walk-forward", json=body)

    oversold = {"target": "signal", "name": "oversold", "values": [5, 10]}
    assert walk_forward({"target": "settings", "owner": "account", "name": "equity", "values": [1e4, 2e4]}).status_code == 400
    assert walk_forward(oversold, metric="trades").status_code == 400
    assert walk_forward(oversold, scheme="expanding").status_code == 422
    assert walk_forward(oversold, settings={"walk_forward": {"windows": 25}}).status_code == 400
    too_short = walk_forward(oversold, settings={"walk_forward": {"windows": 20, "in_sample_ratio": 10}})
    assert too_short.status_code == 400 and "too few for 20 windows" in too_short.json()["detail"]


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


# --- Pinned runs and the trade journal ----------------------------------------------------------------

SNAPSHOT = {"kind": "backtest", "ticker": "SPY", "equity": {"time": ["2026-01-02"], "value": [100000.0]}}


def pinned_run(slot: int, run_id: str | None = None) -> dict:
    return {
        "id": run_id or f"run-{slot}",
        "slot": slot,
        "name": f"SPY run {slot}",
        "hidden": False,
        "pinned_at": "2026-10-18T09:00:00.000Z",
        "format": 7,
        "snapshot": SNAPSHOT,
    }


def test_runs_are_pinned_renamed_and_unpinned(client):
    assert client.get("/api/runs").json() == []
    created = client.post("/api/runs", json=pinned_run(2))
    assert created.status_code == 201 and created.json() == pinned_run(2)
    client.post("/api/runs", json=pinned_run(1))
    assert [run["slot"] for run in client.get("/api/runs").json()] == [1, 2]

    renamed = client.patch("/api/runs/run-2", json={"name": "baseline", "hidden": True}).json()
    assert (renamed["name"], renamed["hidden"], renamed["snapshot"]) == ("baseline", True, SNAPSHOT)
    assert client.patch("/api/runs/run-2", json={"hidden": False}).json()["name"] == "baseline"

    assert client.delete("/api/runs/run-2").status_code == 204
    assert [run["id"] for run in client.get("/api/runs").json()] == ["run-1"]
    assert client.delete("/api/runs").status_code == 204
    assert client.get("/api/runs").json() == []


def test_run_conflicts_and_unknown_runs(client):
    client.post("/api/runs", json=pinned_run(1))
    taken = client.post("/api/runs", json=pinned_run(1, "other"))
    assert taken.status_code == 409 and "Slot 1 is taken" in taken.json()["detail"]
    assert client.post("/api/runs", json=pinned_run(2, "run-1")).status_code == 409
    assert client.post("/api/runs", json=pinned_run(9)).status_code == 422
    assert client.post("/api/runs", json=pinned_run(2) | {"color": "red"}).status_code == 422
    assert client.patch("/api/runs/missing", json={"name": "x"}).status_code == 404
    missing = client.delete("/api/runs/missing")
    assert missing.status_code == 404 and missing.json()["detail"] == "No pinned run missing"


def test_runs_are_kept_in_the_database_given(watchlists, tmp_path):
    database = Database(tmp_path / "tradescan.db")
    first = TestClient(create_app(Settings(), FakeProvider({}), watchlists, database=database))
    first.post("/api/runs", json=pinned_run(1))
    second = TestClient(create_app(Settings(), FakeProvider({}), watchlists, database=Database(tmp_path / "tradescan.db")))
    assert [run["id"] for run in second.get("/api/runs").json()] == ["run-1"]


TRADE = {
    "ticker": " SPY ",
    "direction": "long",
    "opened": "2026-03-02",
    "entry_price": 500.0,
    "quantity": 2.0,
    "stop": 490.0,
}


def test_trades_are_logged_closed_and_summarized(client):
    run = {"format": 7, "snapshot": SNAPSHOT | {"name": "baseline"}}
    logged = client.post("/api/journal/trades", json=TRADE | {"notes": "Pullback to SMA", "run": run})
    assert logged.status_code == 201
    trade = logged.json()
    assert trade["ticker"] == "SPY" and trade["run"] == run and trade["is_open"]
    assert (trade["risk"], trade["profit"], trade["r_multiple"]) == (20.0, None, None)

    closed = client.put(
        f"/api/journal/trades/{trade['id']}",
        json=TRADE | {"closed": "2026-03-20", "exit_price": 530.0, "fees": 2.0, "notes": "Target", "run": run},
    ).json()
    assert (closed["is_open"], closed["profit"], closed["r_multiple"]) == (False, 58.0, 2.9)
    assert closed["return_pct"] == pytest.approx(5.8) and closed["created_at"] == trade["created_at"]
    client.post("/api/journal/trades", json=TRADE | {"direction": "short", "stop": 510.0})

    journal = client.get("/api/journal").json()
    assert [item["direction"] for item in journal["trades"]] == ["short", "long"]
    assert journal["summary"] == {
        "open_trades": 1,
        "closed_trades": 1,
        "win_rate_pct": 100.0,
        "average_return_pct": pytest.approx(5.8),
        "r_trades": 1,
        "average_r": 2.9,
        "total_r": 2.9,
    }
    assert client.delete(f"/api/journal/trades/{trade['id']}").status_code == 204
    assert len(client.get("/api/journal").json()["trades"]) == 1


def test_invalid_and_unknown_trades(client):
    wrong_stop = client.post("/api/journal/trades", json=TRADE | {"stop": 510.0})
    assert wrong_stop.status_code == 400 and "must be below the entry price" in wrong_stop.json()["detail"]
    half_exit = client.post("/api/journal/trades", json=TRADE | {"exit_price": 520.0})
    assert half_exit.status_code == 400 and "both its date and its price" in half_exit.json()["detail"]
    assert client.post("/api/journal/trades", json=TRADE | {"quantity": 0}).status_code == 422
    assert client.post("/api/journal/trades", json=TRADE | {"opened": "March"}).status_code == 422
    assert client.put("/api/journal/trades/99", json=TRADE).status_code == 404
    assert client.delete("/api/journal/trades/99").status_code == 404
    assert client.get("/api/journal").json()["trades"] == []
