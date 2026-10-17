import math
from dataclasses import dataclass
from typing import ClassVar

import numpy as np
import pandas as pd
import pytest
from synthetic import FakeProvider, random_walk

from tradescan.backtest.base import BacktestConfig, ExitReason
from tradescan.backtest.portfolio_metrics import contributions
from tradescan.backtest.priority import MomentumPriority, ScorePriority, TickerPriorityRule, priority_rules
from tradescan.backtest.rotation import (
    DEFAULT_RANKING,
    Rebalance,
    RotationConfig,
    VectorizedRotationEngine,
    prepare,
    ranking_rules,
    rebalance_days,
    run_rotation_periods,
    targets,
)
from tradescan.backtest.rotation_metrics import rotation_metrics
from tradescan.backtest.rules import Bars
from tradescan.backtest.trade_rules import RuleChoice
from tradescan.backtest.weighting import EqualWeight, InverseVolatilityWeight, book_weights, weight_rules
from tradescan.config import Settings
from tradescan.services import RotationRequest, build_use_cases
from tradescan.watchlist import Watchlist

NO_COSTS = BacktestConfig(commission_pct=0.0, slippage_pct=0.0)
# 2020-01-01 is a Wednesday: with 60 business days, January ends on bar 22 and February on bar 42.
JANUARY, FEBRUARY = 22, 42


@dataclass(frozen=True)
class CloseRank(TickerPriorityRule):
    """Test ranking: the higher the close, the stronger. Also proves new rankings plug in without changes."""

    name: ClassVar[str] = "test_close"
    label: ClassVar[str] = "Close"
    description: ClassVar[str] = "test only"

    def strength(self, bars: Bars) -> np.ndarray:
        return bars.close.copy()


def _ticker(level=100.0, overrides=None, length=60, closes=None):
    """Flat bars at `level` (O=C, H and L 1% away), or bars opening at the previous close for `closes`, with selected
    bars replaced by (open, high, low, close)."""
    if closes is not None:
        close = np.asarray(closes, dtype=float)
        open_ = np.r_[close[0], close[:-1]]
        rows = [(o, max(o, c) * 1.01, min(o, c) * 0.99, c) for o, c in zip(open_, close)]
    else:
        rows = [(level, level * 1.01, level * 0.99, level)] * length
    rows = [(overrides or {}).get(i, row) for i, row in enumerate(rows)]
    index = pd.bdate_range("2020-01-01", periods=len(rows), name="date")
    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=index)
    frame["volume"] = 1_000.0
    return frame


def _levels(*levels, length=60):
    return {name: _ticker(level, length=length) for name, level in zip("ABCD", levels)}


def _run(frames, rotation, ranking=CloseRank(), weighting=EqualWeight(), config=NO_COSTS, safe=None, start=None):
    return VectorizedRotationEngine().run(frames, config, rotation, ranking, weighting, safe, start)


def _trades(result):
    return [(item.ticker, item.trade.exit_reason) for item in result.trades]


# --- Calendar and rules --------------------------------------------------------------------------------


def test_rebalance_days_are_the_last_day_of_every_week_or_month_but_the_last():
    calendar = pd.bdate_range("2020-01-01", periods=60)
    assert calendar[rebalance_days(calendar, Rebalance.MONTHLY)].strftime("%m-%d").tolist() == ["01-31", "02-28"]
    weekly = calendar[rebalance_days(calendar, Rebalance.WEEKLY)]
    assert weekly[0] == pd.Timestamp("2020-01-03") and set(weekly.dayofweek) == {4}
    assert calendar[-1] == pd.Timestamp("2020-03-24") and weekly[-1] == pd.Timestamp("2020-03-20")  # that week goes on


def test_rankings_are_the_priority_rules_that_do_not_read_the_scanner():
    names = [rule.name for rule in ranking_rules(priority_rules)]
    assert names == ["relative_strength", "momentum"] and DEFAULT_RANKING in names
    with pytest.raises(ValueError, match="scanner"):
        _run(_levels(100, 200), RotationConfig(holdings=1, absolute_lookback=0), ranking=ScorePriority())


def test_weightings_are_registered_and_inverse_volatility_follows_one_over_the_volatility():
    assert weight_rules.names() == ["equal", "inverse_volatility"]
    calm = _ticker(closes=100 * np.cumprod([1.0] + [1.01, 1 / 1.01] * 40))
    wild = _ticker(closes=100 * np.cumprod([1.0] + [1.02, 1 / 1.02] * 40))
    rule = InverseVolatilityWeight(lookback=10)
    calm_weight, wild_weight = (rule.raw(Bars.from_frame(df, 14)) for df in (calm, wild))
    assert np.isnan(calm_weight[:10]).all() and not np.isnan(calm_weight[10:]).any()
    assert calm_weight[-1] / wild_weight[-1] == pytest.approx(2.0, rel=0.02)
    assert np.isnan(rule.raw(Bars.from_frame(_ticker(100.0), 14))[20:]).all()  # flat closes have no volatility


def test_book_weights_give_each_pick_one_slot_on_average():
    assert book_weights(np.array([2.0, 1.0]), 2) == pytest.approx([2 / 3, 1 / 3])
    assert book_weights(np.array([1.0, 1.0]), 4) == pytest.approx([0.25, 0.25])


# --- Picks, orders and holdings ------------------------------------------------------------------------


def test_the_strongest_tickers_are_bought_at_the_next_open_with_equal_slots():
    result = _run(_levels(100, 200, 300, 400), RotationConfig(holdings=2, absolute_lookback=0))
    assert result.equity.index[0] == pd.Timestamp("2020-01-31")  # the first rebalance with a pick
    assert result.rebalances == 2 and result.orders == 2  # February keeps the same targets
    held = {item.ticker: item.trade for item in result.trades}
    assert set(held) == {"D", "C"}
    assert (held["D"].size, held["C"].size) == (125, 166)  # 50_000 / 400 and 50_000 / 300, in whole lots
    assert held["D"].entry_date == pd.Timestamp("2020-02-03") and held["D"].exit_reason == ExitReason.OPEN
    assert result.equity.iloc[-1] == pytest.approx(100_000.0)
    assert result.holdings.iloc[0] == 0 and result.holdings.iloc[-1] == 2


def test_a_ticker_that_drops_out_is_sold_and_only_the_differences_trade():
    frames = _levels(100, 200, 300, 400)
    frames["A"] = _ticker(100.0, overrides={i: (500.0, 505.0, 495.0, 500.0) for i in range(30, 60)})
    result = _run(frames, RotationConfig(holdings=2, absolute_lookback=0))
    assert _trades(result) == [("C", ExitReason.REBALANCE), ("D", ExitReason.OPEN), ("A", ExitReason.OPEN)]
    sold = result.trades[0].trade
    assert sold.exit_date == pd.Timestamp("2020-03-02") and sold.pnl == pytest.approx(0.0)
    assert math.isnan(sold.r_multiple)
    # February buys A and sells C; D already holds its target.
    assert result.orders == 4


def test_fills_take_the_slippage_and_the_commission():
    config = BacktestConfig(commission_pct=0.1, slippage_pct=0.1)
    # Only January rebalances: February would trim a share, since the costs left less equity.
    result = _run(_levels(100, 200, 300, 400, length=40), RotationConfig(holdings=1, absolute_lookback=0), config=config)
    trade = result.trades[0].trade
    assert trade.entry_price == pytest.approx(400.4) and trade.size == 250
    fee = 0.001 * 250 * 400.4
    assert trade.pnl == pytest.approx(250 * (400.0 - 400.4) - fee)
    assert result.commissions == pytest.approx(fee) and result.traded_value == pytest.approx(250 * 400.4)
    assert result.equity.iloc[-1] == pytest.approx(100_000.0 + trade.pnl)


def test_shares_round_down_to_whole_lots():
    config = BacktestConfig(commission_pct=0.0, slippage_pct=0.0, lot_size=10.0)
    result = _run(_levels(100, 200, 300, 400), RotationConfig(holdings=2, absolute_lookback=0), config=config)
    assert sorted(item.trade.size for item in result.trades) == [120, 160]


def test_a_failed_absolute_momentum_moves_the_slot_to_the_safe_asset_or_to_cash():
    frames = {
        "UP": _ticker(closes=np.linspace(100, 160, 60)),
        "DOWN": _ticker(closes=np.linspace(400, 340, 60)),
    }
    rotation = RotationConfig(holdings=2, absolute_lookback=10, safe_asset="SAFE")
    safe = _ticker(50.0)
    setup = prepare(frames, NO_COSTS, rotation, CloseRank(), EqualWeight(), safe)
    chosen = targets(setup, rotation, JANUARY)
    assert [(pick.ticker, pick.held) for pick in chosen.picks] == [("DOWN", False), ("UP", True)]
    assert chosen.picks[0].momentum < 0 < chosen.picks[1].momentum
    assert (chosen.safe_pct, chosen.cash_pct) == (pytest.approx(50.0), pytest.approx(0.0))

    result = _run({ticker: df.iloc[:40] for ticker, df in frames.items()}, rotation, safe=safe)  # January only
    assert {item.ticker for item in result.trades} == {"UP", "SAFE"}
    assert result.tickers == ("UP", "DOWN", "SAFE")
    assert next(item.trade.size for item in result.trades if item.ticker == "SAFE") == 1_000  # 50_000 / 50
    assert result.safe_pct.iloc[1] == pytest.approx(50.0, abs=1.0)

    in_cash = _run(frames, RotationConfig(holdings=2, absolute_lookback=10))
    assert {item.ticker for item in in_cash.trades} == {"UP"}
    assert in_cash.targets.cash_pct == pytest.approx(50.0)


def test_a_safe_asset_from_the_watchlist_adds_to_its_own_slot():
    frames = {"UP": _ticker(closes=np.linspace(100, 160, 60)), "DOWN": _ticker(closes=np.linspace(400, 340, 60))}
    rotation = RotationConfig(holdings=2, absolute_lookback=10, safe_asset="UP")
    chosen = targets(prepare(frames, NO_COSTS, rotation, CloseRank(), EqualWeight()), rotation, JANUARY)
    assert chosen.weights == {0: pytest.approx(1.0)} and chosen.safe_pct == pytest.approx(50.0)


def test_inverse_volatility_gives_the_calmer_pick_the_larger_share():
    calm = _ticker(closes=100 * np.cumprod([1.0] + [1.01, 1 / 1.01] * 29 + [1.0]))
    wild = _ticker(closes=50 * np.cumprod([1.0] + [1.02, 1 / 1.02] * 29 + [1.0]))
    rotation = RotationConfig(holdings=2, absolute_lookback=0)
    setup = prepare({"CALM": calm, "WILD": wild}, NO_COSTS, rotation, CloseRank(), InverseVolatilityWeight(lookback=10))
    picks = targets(setup, rotation, JANUARY).picks
    assert [pick.ticker for pick in picks] == ["CALM", "WILD"]
    assert picks[0].weight_pct == pytest.approx(200 / 3, rel=0.02) and picks[1].weight_pct == pytest.approx(100 / 3, rel=0.02)


def test_the_run_starts_at_the_first_rebalance_with_a_ranking():
    frames = {"A": _ticker(closes=np.linspace(100, 130, 60)), "B": _ticker(closes=np.linspace(100, 110, 60))}
    result = _run(frames, RotationConfig(holdings=1, absolute_lookback=0), ranking=MomentumPriority(lookback=30, skip=0))
    assert result.equity.index[0] == pd.Timestamp("2020-02-28") and result.rebalances == 1
    assert [item.ticker for item in result.trades] == ["A"]


def test_a_ticker_whose_bars_end_keeps_its_holding_and_the_rest_is_shared_out():
    frames = _levels(100, 200, 300)
    frames["D"] = _ticker(400.0, length=31)
    result = _run(frames, RotationConfig(holdings=2, absolute_lookback=0))
    held = {item.ticker: item.trade for item in result.trades}
    assert held["D"].exit_reason == ExitReason.OPEN and held["D"].exit_date == frames["D"].index[-1]
    # In February D cannot be sold: C keeps its 166 shares, B gets the other half of the 50_000 left over.
    assert held["C"].size == 166 and held["B"].size == 125
    assert result.exposure_pct.max() <= 100.0


# --- Whole runs ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def walks():
    return {f"T{i}": random_walk(1500, seed=i) for i in range(8)}


@pytest.mark.parametrize("rebalance", list(Rebalance))
def test_the_equity_is_the_initial_equity_plus_every_holdings_pnl(walks, rebalance):
    rotation = RotationConfig(holdings=3, absolute_lookback=126, rebalance=rebalance, safe_asset="SAFE")
    safe = random_walk(1500, seed=99, volatility=0.005)
    result = _run(walks, rotation, ranking=MomentumPriority(), weighting=InverseVolatilityWeight(), config=BacktestConfig(), safe=safe)
    assert result.equity.iloc[-1] - 100_000.0 == pytest.approx(sum(item.trade.pnl for item in result.trades))
    assert result.holdings.max() <= 4 and result.unfilled == 0
    shares = contributions(result, 100_000.0)
    assert [row.ticker for row in shares] == [*walks, "SAFE"]
    assert sum(row.pnl for row in shares) == pytest.approx(result.equity.iloc[-1] - 100_000.0)


def test_decisions_only_read_the_bars_up_to_their_close(walks):
    rotation = RotationConfig(holdings=2, absolute_lookback=126)
    full = _run(walks, rotation, ranking=MomentumPriority(), config=BacktestConfig())
    cut = pd.Timestamp("2016-06-15")
    early = _run({ticker: df.loc[:cut] for ticker, df in walks.items()}, rotation, ranking=MomentumPriority(), config=BacktestConfig())
    pd.testing.assert_series_equal(early.equity, full.equity.loc[: early.equity.index[-1]])


def test_periods_trade_before_and_from_the_split_with_fresh_equity(walks):
    rotation = RotationConfig(holdings=2, absolute_lookback=0)
    split = pd.Timestamp("2016-01-04")
    periods = run_rotation_periods(VectorizedRotationEngine(), walks, BacktestConfig(), rotation, MomentumPriority(), EqualWeight(), None, split)
    assert periods.in_sample.equity.index[-1] < split
    assert periods.out_of_sample.equity.index[0] >= split
    assert periods.out_of_sample.equity.iloc[0] == 100_000.0
    assert all(item.trade.entry_date > split for item in periods.out_of_sample.trades)


def test_metrics_compare_the_benchmark_and_report_how_the_rotation_traded(walks):
    rotation = RotationConfig(holdings=2, absolute_lookback=0)
    result = _run(walks, rotation, ranking=MomentumPriority(), config=BacktestConfig())
    benchmark = walks["T0"]["close"]
    report = rotation_metrics(result, benchmark, 252)
    dates = result.equity.index
    assert report.metrics.buy_hold_pct == pytest.approx((benchmark[dates[-1]] / benchmark[dates[0]] - 1) * 100)
    assert math.isnan(report.metrics.expectancy_r) and report.metrics.trades == sum(t.trade.is_closed for t in result.trades)
    stats = report.stats
    assert stats.rebalances == result.rebalances and stats.max_holdings == 2
    assert stats.average_cash_pct == pytest.approx(100.0 - stats.average_exposure_pct)
    years = (len(dates) - 1) / 252
    assert stats.turnover_pct == pytest.approx(result.traded_value / 2 / result.equity.mean() / years * 100)


# --- Use case ------------------------------------------------------------------------------------------


def _use_case(frames):
    return build_use_cases(Settings(), FakeProvider(frames)).rotation


@pytest.fixture(scope="module")
def market(walks):
    return {**walks, "SPY": random_walk(1500, seed=50), "TLT": random_walk(1500, seed=51, volatility=0.005)}


def test_the_use_case_runs_the_watchlist_with_a_safe_asset_and_both_periods(market):
    universe = Watchlist("demo", ("T0", "T1", "T2", "T3", "NODATA"), benchmark="SPY")
    report = _use_case(market).run(
        RotationRequest(
            universe,
            ranking=RuleChoice("relative_strength"),
            weighting=RuleChoice("inverse_volatility", {"lookback": 20}),
            rebalance=Rebalance.WEEKLY,
            safe_asset=" tlt ",
            settings={"rotation": {"holdings": 2, "absolute_lookback": 63}},
        )
    )
    assert report.rotation == RotationConfig(holdings=2, absolute_lookback=63, rebalance=Rebalance.WEEKLY, safe_asset="TLT")
    assert report.weighting == InverseVolatilityWeight(lookback=20) and report.benchmark == "SPY"
    assert report.benchmark_close.index.equals(report.result.equity.index)
    assert report.split is not None and report.in_sample is not None and report.out_of_sample is not None
    assert report.split.in_sample[0] == report.result.equity.index[0]
    assert [row.ticker for row in report.contributions] == ["T0", "T1", "T2", "T3", "TLT"]
    assert report.missing == ["NODATA"]


def test_the_use_case_defaults_to_momentum_with_equal_weights_and_cash(market):
    report = _use_case(market).run(RotationRequest(Watchlist("demo", ("T0", "T1"))))
    assert (report.ranking, report.weighting) == (MomentumPriority(), EqualWeight())
    assert report.rotation == RotationConfig() and report.benchmark == "SPY"


def test_the_use_case_rejects_what_it_cannot_run(market):
    use_case = _use_case(market)
    universe = Watchlist("demo", ("T0", "T1"))
    with pytest.raises(ValueError, match="Unknown ranking rule 'score'. Use: relative_strength, momentum"):
        use_case.run(RotationRequest(universe, ranking=RuleChoice("score")))
    with pytest.raises(ValueError, match="No data for the safe asset IEF"):
        use_case.run(RotationRequest(universe, safe_asset="IEF"))
    with pytest.raises(ValueError, match="No data for the benchmark QQQ"):
        use_case.run(RotationRequest(universe, benchmark="QQQ"))
    with pytest.raises(ValueError, match="No data for any ticker"):
        use_case.run(RotationRequest(Watchlist("none", ("NODATA",))))
    short = _use_case({"T0": market["T0"].iloc[:200], "SPY": market["SPY"]})
    with pytest.raises(ValueError, match="shorter than the ranking"):
        short.run(RotationRequest(Watchlist("demo", ("T0",))))
