import numpy as np
import pandas as pd
import pytest
from synthetic import FakeProvider, random_walk

from tradescan import cli


@pytest.fixture
def provider(monkeypatch):
    frames = {
        "AAA": random_walk(1500, seed=1),
        "BBB": random_walk(1500, seed=2),
        "CCC": random_walk(1500, seed=3),
        "SPY": random_walk(1500, seed=4),
    }
    fake = FakeProvider(frames)
    monkeypatch.setattr(cli, "_provider", lambda settings, args: fake)
    return fake


def test_list_signals_runs():
    assert cli.main(["list-signals"]) == 0


def test_scan_exports_hits(provider, tmp_path):
    target = tmp_path / "hits.csv"
    code = cli.main(["scan", "--tickers", "AAA,BBB,CCC,ZZZ", "--fresh", "10", "--min-score", "-10", "--export", str(target)])
    assert code == 0
    hits = pd.read_csv(target)
    assert not hits.empty
    assert {"ticker", "dir", "score", "stop", "size", "edge N"} <= set(hits.columns)
    assert hits["score"].is_monotonic_decreasing
    assert provider.calls[0][0] == ("AAA", "BBB", "CCC", "ZZZ", "SPY")


def test_market_and_edge(provider, tmp_path):
    assert cli.main(["market", "--tickers", "AAA,BBB", "--benchmark", "SPY"]) == 0
    target = tmp_path / "edge.json"
    code = cli.main(["edge", "--tickers", "AAA,BBB,CCC", "--family", "breakout", "--horizons", "5,10", "--export", str(target)])
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
    code = cli.main(["backtest", "AAA", "connors_rsi2_long", "--entry", "limit", "--exits", "time", "--max-hold", "3", "--export", str(target)])
    assert code == 0
    trades = pd.read_csv(target)
    assert not trades.empty and set(trades["exit_reason"]) <= {"stop", "time", "open"}
    assert cli.main(["backtest", "AAA", "connors_rsi2_long", "--exits", "none"]) == 0


def test_errors_are_reported_not_raised(provider):
    assert cli.main(["backtest", "AAA", "no_such_signal"]) == 2
    assert cli.main(["backtest", "AAA", "golden_cross", "--exits", "time", "--target-r", "3"]) == 2
    assert cli.main(["backtest", "AAA", "golden_cross", "--exits", "trailing"]) == 2
    assert cli.main(["scan", "--watchlist", "missing-list"]) == 2
