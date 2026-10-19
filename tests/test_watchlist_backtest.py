import math
import pickle
from dataclasses import astuple, replace

import numpy as np
import pytest
from tests.synthetic import FakeProvider, random_walk

from tradescan.backtest.base import BacktestConfig
from tradescan.backtest.pooled import BREAK_EVEN, pool_trades, spread
from tradescan.backtest.tickers import Period, TickerJob
from tradescan.backtest.trade_rules import RuleChoice, TradeRules
from tradescan.config import Settings
from tradescan.parallel import ProcessRunner
from tradescan.services import BacktestRequest, WatchlistBacktestRequest, build_use_cases
from tradescan.signals import default_registry
from tradescan.watchlist import Watchlist

# --- Pooled trades and spreads -------------------------------------------------------------------


def test_pooled_trades_take_every_ticker_together():
    pooled = pool_trades([np.array([2.0, -1.0]), np.array([]), np.array([1.0, -1.0, 3.0])])
    assert pooled.trades == 5
    assert pooled.win_rate_pct == pytest.approx(60.0)
    assert pooled.expectancy_r == pytest.approx(0.8)
    assert pooled.profit_factor_r == pytest.approx(3.0)
    r = np.array([2.0, -1.0, 1.0, -1.0, 3.0])
    assert pooled.sqn == pytest.approx(math.sqrt(5) * r.mean() / r.std(ddof=1))


def test_pooled_trades_without_trades_or_losers():
    empty = pool_trades([])
    assert empty.trades == 0 and math.isnan(empty.expectancy_r) and math.isnan(empty.profit_factor_r)
    assert math.isinf(pool_trades([np.array([1.0, 2.0])]).profit_factor_r)


def test_spread_quantiles_and_break_even():
    result = spread([3.0, -1.0, math.nan, 1.0, 5.0], break_even=0.0)
    assert result.tickers == 4
    assert (result.minimum, result.p25, result.median, result.p75, result.maximum) == (-1.0, 0.5, 2.0, 3.5, 5.0)
    assert result.median == pytest.approx(float(np.median([3.0, -1.0, 1.0, 5.0])))
    assert result.p25 == pytest.approx(float(np.quantile([3.0, -1.0, 1.0, 5.0], 0.25)))
    assert result.above_break_even_pct == pytest.approx(75.0)
    assert math.isnan(spread([1.0, 2.0]).above_break_even_pct)  # no break-even given


def test_spread_keeps_infinite_profit_factors_largest():
    result = spread([0.5, math.inf, math.inf, 2.0], BREAK_EVEN["profit_factor"])
    assert result.median == math.inf and result.maximum == math.inf and result.p25 == pytest.approx(1.625)
    assert result.above_break_even_pct == pytest.approx(75.0)
    empty = spread([math.nan])
    assert empty.tickers == 0 and math.isnan(empty.median)


# --- The per-ticker job --------------------------------------------------------------------------


def test_ticker_job_is_picklable_and_skips_the_split_on_short_history():
    job = TickerJob(default_registry.create("connors_rsi2_long"), TradeRules(), BacktestConfig())
    assert pickle.loads(pickle.dumps(job)).signal.name == "connors_rsi2_long"
    run = job(("TINY", random_walk(100, seed=2)))
    assert run.split is None and run.in_sample is None and run.out_of_sample is None
    assert run.period(Period.FULL) is run.full and run.period(Period.OUT_OF_SAMPLE) is None


# --- The use case ----------------------------------------------------------------------------------


@pytest.fixture
def frames():
    return {
        "AAA": random_walk(1500, seed=1),
        "BBB": random_walk(1500, seed=2),
        "CCC": random_walk(1200, seed=3),
        "TINY": random_walk(100, seed=4),
        "SPY": random_walk(1600, seed=5),
        "QQQ": random_walk(1600, seed=6),
    }


SETUP = BacktestRequest(ticker="", signal="connors_rsi2_long", period="max")
DEMO = Watchlist("demo", ("AAA", "BBB", "NOPE", "CCC", "TINY"))


def _same(left, right):
    """Equal metrics; NaN (no trades) equals NaN."""
    np.testing.assert_equal(astuple(left), astuple(right))


def _run(frames, setup=SETUP, universe=DEMO, runner=None, provider=None):
    use_cases = build_use_cases(Settings(), provider or FakeProvider(frames), runner=runner)
    return use_cases.watchlist_backtest.run(WatchlistBacktestRequest(universe, setup))


def test_every_ticker_row_is_its_single_backtest(frames):
    report = _run(frames)
    assert [row.ticker for row in report.rows] == ["AAA", "BBB", "CCC", "TINY"]
    assert report.missing == ["NOPE"] and report.base.benchmark is None
    backtest = build_use_cases(Settings(), FakeProvider(frames)).backtest
    for row in report.rows:
        single = backtest.run(replace(SETUP, ticker=row.ticker))
        run = single.runs[0]
        _same(row.run.full.metrics, run.metrics)
        assert row.run.split == single.split
        assert (row.start, row.end) == (single.close.index[0], single.close.index[-1])
        if single.split is None:
            assert row.run.in_sample is None
            continue
        _same(row.run.in_sample.metrics, run.periods.in_sample)
        _same(row.run.out_of_sample.metrics, run.periods.out_of_sample)
        closed = [trade.r_multiple for trade in run.result.trades if trade.is_closed]
        assert row.run.full.r_multiples.tolist() == closed


def test_periods_pool_trades_and_spread_metrics(frames):
    report = _run(frames)
    full = report.periods[Period.FULL]
    assert full.tickers == 4 and report.periods[Period.OUT_OF_SAMPLE].tickers == 3  # TINY is too short to split
    _same(full.pooled, pool_trades(row.run.full.r_multiples for row in report.rows))
    assert full.pooled.trades == sum(row.run.full.metrics.trades for row in report.rows)
    oos = report.periods[Period.OUT_OF_SAMPLE]
    values = [row.run.out_of_sample.metrics.sharpe for row in report.rows if row.run.out_of_sample]
    _same(oos.spreads["sharpe"], spread(values, 0.0))
    assert set(oos.spreads) == {"total_return_pct", "cagr_pct", "sharpe", "sortino", "max_drawdown_pct", "trades",
                                "win_rate_pct", "profit_factor", "expectancy_r", "sqn", "exposure_pct", "buy_hold_pct"}  # fmt: skip
    assert math.isnan(oos.spreads["trades"].above_break_even_pct)


def test_the_market_filter_compares_the_watchlist_benchmark_unless_the_setup_names_one(frames):
    provider = FakeProvider(frames)
    setup = replace(SETUP, filters=(RuleChoice("market"),))
    universe = Watchlist("demo", ("AAA", "BBB"), benchmark="QQQ")
    report = _run(frames, setup, universe, provider=provider)
    assert report.base.benchmark == "QQQ" and provider.calls[0][0] == ("AAA", "BBB", "QQQ")
    single = build_use_cases(Settings(), FakeProvider(frames)).backtest.run(replace(setup, ticker="AAA", benchmark="QQQ"))
    _same(report.rows[0].run.full.metrics, single.runs[0].metrics)

    assert _run(frames, replace(setup, benchmark="spy"), universe).base.benchmark == "SPY"
    assert _run(frames, setup, Watchlist("demo", ("AAA",))).base.benchmark == "SPY"  # the configured one
    assert _run(frames, SETUP, universe).base.benchmark is None  # no filter reads it


def test_missing_data_is_an_error(frames):
    with pytest.raises(ValueError, match="No data for any ticker of none"):
        _run(frames, universe=Watchlist("none", ("NOPE",)))
    with pytest.raises(ValueError, match="No data for the benchmark XYZ, which the market filter compares"):
        _run(frames, replace(SETUP, filters=(RuleChoice("market"),), benchmark="XYZ"))
    with pytest.raises(ValueError, match="oversold must be between"):
        _run(frames, replace(SETUP, params={"oversold": 0}))


def test_worker_processes_match_one_process(frames):
    one = _run(frames)
    many = _run(frames, runner=ProcessRunner(workers=2, min_items=1))
    for left, right in zip(many.rows, one.rows, strict=True):
        _same(left.run.full.metrics, right.run.full.metrics)
    _same(many.periods[Period.IN_SAMPLE].pooled, one.periods[Period.IN_SAMPLE].pooled)
