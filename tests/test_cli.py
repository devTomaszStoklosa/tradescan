import numpy as np
import pandas as pd
import pytest

from tests.synthetic import FakeProvider, random_walk
from tradescan import cli
from tradescan.cli import inputs, wiring


@pytest.fixture
def provider(monkeypatch):
    frames = {
        "AAA": random_walk(1500, seed=1),
        "BBB": random_walk(1500, seed=2),
        "CCC": random_walk(1500, seed=3),
        "SPY": random_walk(1500, seed=4),
    }
    fake = FakeProvider(frames)
    monkeypatch.setattr(wiring, "provider", lambda settings, args: fake)
    return fake


def test_list_signals_runs():
    assert cli.main(["list-signals"]) == 0


def test_scan_exports_hits(provider, tmp_path):
    target = tmp_path / "hits.csv"
    code = cli.main(
        ["scan", "--tickers", "AAA,BBB,CCC,ZZZ", "--fresh", "10", "--min-score", "-10", "--export", str(target)]
    )
    assert code == 0
    hits = pd.read_csv(target)
    assert not hits.empty
    assert {"ticker", "dir", "score", "stop", "size", "edge N"} <= set(hits.columns)
    assert hits["score"].is_monotonic_decreasing
    assert provider.calls[0][0] == ("AAA", "BBB", "CCC", "ZZZ", "SPY")


def test_market_and_edge(provider, tmp_path):
    assert cli.main(["market", "--tickers", "AAA,BBB", "--benchmark", "SPY"]) == 0
    target = tmp_path / "edge.json"
    code = cli.main(
        ["edge", "--tickers", "AAA,BBB,CCC", "--family", "breakout", "--horizons", "5,10", "--export", str(target)]
    )
    assert code == 0
    edge = pd.read_json(target)
    assert set(edge["family"]) == {"breakout"}
    assert {"N 5d", "vs base% 10d"} <= set(edge.columns)


def test_backtest_both_engines(provider, tmp_path):
    pytest.importorskip("backtrader")
    target = tmp_path / "trades.csv"
    assert cli.main(["backtest", "AAA", "donchian_breakout", "--engine", "both", "--export", str(target)]) == 0
    trades = pd.read_csv(target)
    counts = trades["engine"].value_counts()
    assert counts["vectorized"] == counts["cerebro"] > 0
    assert np.allclose(
        trades.loc[trades.engine == "vectorized", "pnl"].to_numpy(),
        trades.loc[trades.engine == "cerebro", "pnl"].to_numpy(),
    )


def test_backtest_entry_and_exit_options(provider, tmp_path):
    target = tmp_path / "trades.csv"
    code = cli.main(
        [
            "backtest",
            "AAA",
            "connors_rsi2_long",
            "--entry",
            "limit",
            "--exits",
            "time",
            "--max-hold",
            "3",
            "--export",
            str(target),
        ]
    )
    assert code == 0
    trades = pd.read_csv(target)
    assert not trades.empty
    assert set(trades["exit_reason"]) <= {"stop", "time", "open"}
    assert cli.main(["backtest", "AAA", "connors_rsi2_long", "--exits", "none"]) == 0


def test_backtest_pyramiding_options(provider, tmp_path, capsys):
    target = tmp_path / "trades.csv"
    code = cli.main(
        ["backtest", "AAA", "donchian_breakout", "--max-units", "3", "--add-every-atr", "1", "--export", str(target)]
    )
    assert code == 0
    assert "pyramiding up to 3 units 1 ATR apart" in " ".join(capsys.readouterr().out.split())
    trades = pd.read_csv(target)
    assert trades["units"].max() > 1
    assert trades["units"].max() <= 3
    assert cli.main(["portfolio-backtest", "donchian_breakout", "-t", "AAA,BBB", "--max-units", "2"]) == 2
    assert "does not pyramid" in capsys.readouterr().out


def test_backtest_filter_options(provider, capsys):
    assert cli.main(["backtest", "AAA", "connors_rsi2_long", "--filters", "trend,market", "--benchmark", "bbb"]) == 0
    output = capsys.readouterr().out
    assert "filters: Close above SMA(200)" in output
    assert "(benchmark BBB)" in output
    assert provider.calls[-1][0] == ("AAA", "BBB")
    assert cli.main(["backtest", "AAA", "connors_rsi2_long", "--filters", "nope"]) == 2
    assert inputs.axis("filter.trend.period=100:200:50").key == "filter.trend.period"


def test_backtest_out_of_sample_option(provider, capsys):
    assert cli.main(["backtest", "AAA", "connors_rsi2_long", "--oos", "20"]) == 0
    assert "out-of-sample (last 20%)" in capsys.readouterr().out
    assert cli.main(["backtest", "AAA", "connors_rsi2_long", "--oos", "70"]) == 2


def test_sweep_exports_every_combination(provider, tmp_path, capsys):
    target = tmp_path / "sweep.csv"
    code = cli.main([
        "sweep", "AAA", "connors_rsi2_long", "--axis", "signal.oversold=5:20:5", "--axis", "exit.target.target_r=1,2.5",
        "--metric", "expectancy_r", "--export", str(target),
    ])  # fmt: skip
    assert code == 0
    output = capsys.readouterr().out
    assert "8 combinations" in output
    assert "Out-of-sample (last 30%)" in output
    assert "oversold=15" in output
    cells = pd.read_csv(target)
    assert list(cells["signal.oversold"]) == [5, 5, 10, 10, 15, 15, 20, 20]
    assert list(cells["exit.target.target_r"]) == [1, 2.5] * 4
    assert {"is_sharpe", "oos_expectancy_r", "error"} <= set(cells.columns)


def test_walk_forward_prints_every_window_and_exports_them(provider, tmp_path, capsys):
    target = tmp_path / "windows.csv"
    code = cli.main([
        "walk-forward", "AAA", "connors_rsi2_long",
        "--axis", "signal.oversold=5:20:5", "--axis", "exit.target.target_r=1.5,2.5",
        "--windows", "4", "--in-sample-ratio", "2", "--min-trades", "5", "--metric", "expectancy_r",
        "--export", str(target),
    ])  # fmt: skip
    assert code == 0
    output = " ".join(capsys.readouterr().out.split())  # without the console's line breaks
    assert "8 combinations" in output
    assert "4 rolling windows of 250 bars, each after an in-sample window of 500 bars" in output
    assert "highest expectancy_r with at least 5 trades" in output
    assert "Walk-forward efficiency" in output
    assert "unchanged setup" in output
    assert "Next setting: " in output
    windows = pd.read_csv(target)
    assert list(windows["window"]) == [1, 2, 3, 4]
    assert {
        "is_start",
        "oos_end",
        "traded_from",
        "signal.oversold",
        "exit.target.target_r",
        "is_sharpe",
        "oos_trades",
    } <= set(windows.columns)


def test_walk_forward_refuses_an_out_of_sample_share(provider):
    assert cli.main(["walk-forward", "AAA", "connors_rsi2_long", "--axis", "signal.oversold=5,10", "--oos", "20"]) == 2
    assert cli.main(["walk-forward", "AAA", "connors_rsi2_long", "--axis", "settings.account.equity=1e4,2e4"]) == 2


def test_watchlist_backtest_ranks_tickers_and_exports_every_period(provider, tmp_path, capsys):
    target = tmp_path / "tickers.csv"
    code = cli.main([
        "watchlist-backtest", "connors_rsi2_long", "-t", "AAA,BBB,CCC,ZZZ", "--filters", "market", "--top", "2",
        "--metric", "sharpe", "--export", str(target),
    ])  # fmt: skip
    assert code == 0
    output = " ".join(capsys.readouterr().out.split())  # without the console's line breaks
    assert "No data for: ZZZ" in output
    assert "3 tickers of custom" in output
    assert "(benchmark SPY)" in output
    assert "2 of 3 tickers, best sharpe first" in output
    assert "Spread of sharpe across tickers" in output
    assert "trades pooled, in R" in output
    assert provider.calls[-1][0] == ("AAA", "BBB", "CCC", "ZZZ", "SPY")
    rows = pd.read_csv(target)
    assert list(rows["ticker"]) == ["AAA", "BBB", "CCC"]
    assert {"start", "oos_start", "full_sharpe", "is_trades", "oos_expectancy_r"} <= set(rows.columns)
    with pytest.raises(SystemExit):
        cli.main(["watchlist-backtest", "connors_rsi2_long", "-t", "AAA", "--metric", "nope"])


def test_portfolio_backtest_shares_one_equity_and_exports_every_engines_trades(provider, tmp_path, capsys):
    target = tmp_path / "trades.csv"
    code = cli.main([
        "portfolio-backtest", "connors_rsi2_long", "-t", "AAA,BBB,CCC,ZZZ",
        "--max-positions", "2", "--max-exposure", "50", "--priority", "momentum", "--engine", "both",
        "--top", "2", "--export", str(target),
    ])  # fmt: skip
    assert code == 0
    output = " ".join(capsys.readouterr().out.split())
    assert "No data for: ZZZ" in output
    assert "3 tickers of custom with one equity" in output
    assert "at most 2 positions and 50% exposure, priority: Return from 252 bars ago to 21 bars ago" in output
    assert "buy & hold is SPY's" in output
    assert "2 of 3 tickers by P&L (vectorized)" in output
    assert provider.calls[-1][0] == ("AAA", "BBB", "CCC", "ZZZ", "SPY")
    trades = pd.read_csv(target)
    assert set(trades["engine"]) == {"vectorized", "cerebro"}
    assert set(trades["ticker"]) <= {"AAA", "BBB", "CCC"}
    vectorized, cerebro = (
        trades[trades["engine"] == engine].drop(columns="engine") for engine in ("vectorized", "cerebro")
    )
    pd.testing.assert_frame_equal(vectorized.reset_index(drop=True), cerebro.reset_index(drop=True), rtol=1e-6)
    with pytest.raises(SystemExit):
        cli.main(["portfolio-backtest", "connors_rsi2_long", "-t", "AAA", "--priority", "nope"])


def test_portfolio_backtest_ranks_by_the_scan_score(provider, capsys):
    code = cli.main(
        ["portfolio-backtest", "connors_rsi2_long", "-t", "AAA,BBB,CCC", "--max-positions", "1", "--priority", "score"]
    )
    assert code == 0
    output = " ".join(capsys.readouterr().out.split())
    assert (
        "priority: The scanner's confluence score: fresh signals, daily and weekly trend, relative-strength rank"
        in output
    )


def test_rotation_backtest_holds_the_strongest_tickers_and_exports_the_trades(provider, tmp_path, capsys):
    target = tmp_path / "trades.csv"
    code = cli.main([
        "rotation-backtest", "-t", "AAA,BBB,CCC,ZZZ", "--rank", "relative_strength", "--holdings", "2",
        "--rebalance", "weekly", "--weighting", "inverse_volatility",
        "--absolute-lookback", "63", "--safe-asset", "spy",
        "--commission-pct", "0.05", "--top", "2", "--export", str(target),
    ])  # fmt: skip
    assert code == 0
    output = " ".join(capsys.readouterr().out.split())
    assert "No data for: ZZZ" in output
    assert "Top 2 of 3 tickers of custom, rebalanced weekly" in output
    assert "a pick at or below 0 over 63 bars goes to SPY" in output
    assert "Costs 0.05% + 0.05% slippage" in output
    assert "buy & hold is SPY's" in output
    assert "would pick" in output
    assert "% in SPY, " in output
    assert "2 of 4 tickers by P&L (vectorized)" in output
    assert provider.calls[-1][0] == ("AAA", "BBB", "CCC", "ZZZ", "SPY")
    trades = pd.read_csv(target)
    assert set(trades["engine"]) == {"vectorized"}
    assert set(trades["ticker"]) <= {"AAA", "BBB", "CCC", "SPY"}
    assert set(trades["exit_reason"]) <= {"rebalance", "open"}
    with pytest.raises(SystemExit):
        cli.main(["rotation-backtest", "-t", "AAA", "--rank", "score"])


def test_rotation_backtest_on_both_engines_exports_every_engines_trades(provider, tmp_path):
    pytest.importorskip("backtrader")
    target = tmp_path / "trades.csv"
    code = cli.main([
        "rotation-backtest", "-t", "AAA,BBB,CCC", "--holdings", "2", "--engine", "both", "--export", str(target)
    ])  # fmt: skip
    assert code == 0
    trades = pd.read_csv(target)
    assert set(trades["engine"]) == {"vectorized", "cerebro"}
    vectorized, cerebro = (
        trades[trades["engine"] == engine].drop(columns="engine") for engine in ("vectorized", "cerebro")
    )
    assert len(vectorized) > 0
    pd.testing.assert_frame_equal(vectorized.reset_index(drop=True), cerebro.reset_index(drop=True), rtol=1e-6)


def test_backtest_and_sweep_still_take_a_ticker(provider):
    assert cli.build_parser().parse_args(["backtest", "AAA", "connors_rsi2_long"]).ticker == "AAA"
    assert (
        cli.build_parser().parse_args(["sweep", "AAA", "connors_rsi2_long", "--axis", "signal.oversold=5,10"]).signal
        == "connors_rsi2_long"
    )


@pytest.mark.parametrize(
    ("command", "benchmark_help"),
    [
        (
            "backtest",
            "--benchmark BENCHMARK benchmark the market filter compares (default: scan.benchmark from the settings)",
        ),
        (
            "sweep",
            "--benchmark BENCHMARK benchmark the market filter compares (default: scan.benchmark from the settings)",
        ),
        (
            "walk-forward",
            "--benchmark BENCHMARK benchmark the market filter compares (default: scan.benchmark from the settings)",
        ),
        (
            "watchlist-backtest",
            "--benchmark BENCHMARK benchmark the market filter compares "
            "(default: the watchlist's '# benchmark:' line, else scan.benchmark from the settings)",
        ),
        (
            "portfolio-backtest",
            "--benchmark BENCHMARK benchmark for buy & hold and for the market filter "
            "(default: the watchlist's '# benchmark:' line, else scan.benchmark from the settings)",
        ),
    ],
)
def test_benchmark_help_names_each_commands_default(command, benchmark_help, capsys):
    with pytest.raises(SystemExit):
        cli.main([command, "--help"])
    assert benchmark_help in " ".join(capsys.readouterr().out.split())


@pytest.mark.parametrize(
    "axis",
    [
        "oversold=5:20:5",
        "signal.oversold",
        "nope.oversold=1,2",
        "signal.oversold=5:1:1",
        "signal.oversold=1:100:1",
        "signal.oversold=a,b",
    ],
)
def test_sweep_axis_errors(provider, axis):
    assert cli.main(["sweep", "AAA", "connors_rsi2_long", "--axis", axis]) == 2


def test_sweep_float_ranges_have_no_rounding_noise():
    assert inputs.axis("settings.risk.atr_mult=0.1:0.7:0.2").values == (0.1, 0.3, 0.5, 0.7)


def test_errors_are_reported_not_raised(provider):
    assert cli.main(["backtest", "AAA", "no_such_signal"]) == 2
    assert cli.main(["backtest", "AAA", "golden_cross", "--exits", "time", "--target-r", "3"]) == 2
    assert cli.main(["backtest", "AAA", "golden_cross", "--exits", "nope"]) == 2
    assert cli.main(["scan", "--watchlist", "missing-list"]) == 2


def test_serve_keeps_runs_and_the_journal_in_the_db_file(provider, monkeypatch, tmp_path):
    uvicorn = pytest.importorskip("uvicorn")
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    served = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: served.append(app))
    path = tmp_path / "journal" / "trades.db"
    trade = {"ticker": "AAA", "direction": "long", "opened": "2026-03-02", "entry_price": 10.0, "quantity": 5.0}
    assert cli.main(["serve", "--static", str(tmp_path / "no-ui"), "--db", str(path)]) == 0
    first = TestClient(served[0], base_url="http://localhost")
    assert first.post("/api/journal/trades", json=trade).status_code == 201
    assert cli.main(["serve", "--static", str(tmp_path / "no-ui"), "--db", str(path)]) == 0
    second = TestClient(served[1], base_url="http://localhost")
    assert [item["ticker"] for item in second.get("/api/journal").json()["trades"]] == ["AAA"]


@pytest.mark.parametrize(("bind", "host"), [("192.168.1.5", "192.168.1.5:8000"), ("fd00::5", "[fd00::5]:8000")])
def test_serve_answers_the_bound_address_and_this_machine_only(provider, monkeypatch, tmp_path, bind, host):
    uvicorn = pytest.importorskip("uvicorn")
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    served = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: served.append(app))
    serve = ["serve", "--host", bind, "--static", str(tmp_path / "no-ui"), "--db", str(tmp_path / "tradescan.db")]
    assert cli.main(serve) == 0
    client = TestClient(served[0])
    assert client.get("/api/health", headers={"host": host}).status_code == 200
    assert client.get("/api/health", headers={"host": "localhost:8000"}).status_code == 200
    assert client.get("/api/health", headers={"host": "evil.example:8000"}).status_code == 400


def test_serve_refuses_a_file_that_is_not_a_database(provider, monkeypatch, tmp_path):
    uvicorn = pytest.importorskip("uvicorn")
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: pytest.fail("the server must not start"))
    path = tmp_path / "notes.txt"
    path.write_text("not a database " * 100)
    assert cli.main(["serve", "--static", str(tmp_path / "no-ui"), "--db", str(path)]) == 2
