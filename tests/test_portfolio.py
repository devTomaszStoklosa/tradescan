import math
from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
import pandas as pd
import pytest

from tests.synthetic import FakeProvider, random_walk
from tradescan.backtest.allocation import Candidate, PortfolioConfig, allocate, fit, rank
from tradescan.backtest.base import BacktestConfig, ExitReason
from tradescan.backtest.entries import LimitEntry, OrderType, StopEntry
from tradescan.backtest.exits import TargetExit, TimeExit, TrailingStop
from tradescan.backtest.filters import MarketFilter, TrendFilter
from tradescan.backtest.oos import split_history
from tradescan.backtest.portfolio import VectorizedPortfolioEngine, prepare, run_portfolio_periods, shared_calendar
from tradescan.backtest.portfolio_metrics import contributions, portfolio_metrics
from tradescan.backtest.priority import (
    MomentumPriority,
    PriorityInputs,
    RelativeStrengthPriority,
    ScanScore,
    ScorePriority,
    TickerPriorityRule,
    priority_rules,
)
from tradescan.backtest.rules import Bars
from tradescan.backtest.trade_rules import EntryPlan, RuleChoice, TradeRules
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.config import Settings
from tradescan.context import ContextBuilder, Trend
from tradescan.risk import RiskPlanner
from tradescan.scanner import Scanner
from tradescan.scoring import Scorer
from tradescan.services import BacktestRequest, PortfolioRequest, build_context_builder, build_scorer, build_use_cases
from tradescan.signals import Direction, default_registry
from tradescan.signals.base import Family, Signal
from tradescan.watchlist import Watchlist

NO_COSTS = BacktestConfig(risk_pct=1.0, max_position_pct=25.0, commission_pct=0.0, slippage_pct=0.0)
BRACKET = TradeRules(exits=(TargetExit(target_r=2.0), TimeExit(max_hold_bars=5)))


@dataclass(frozen=True)
class ColumnSignal(Signal):
    """Test signal that fires where a ticker's `fire` column is set, so tickers can fire on different bars."""

    side: Direction = Direction.LONG
    name: ClassVar[str] = "column"
    family: ClassVar[Family] = Family.PATTERN
    description: ClassVar[str] = "test only"

    @property
    def direction(self) -> Direction:  # type: ignore[override]
        return self.side

    def condition(self, df: pd.DataFrame) -> pd.Series:
        return df["fire"].astype(bool)


@dataclass(frozen=True)
class ClosePriority(TickerPriorityRule):
    """Test priority: the higher the close, the earlier. Also proves new priorities plug in without changes."""

    name: ClassVar[str] = "test_close"
    label: ClassVar[str] = "Close"
    description: ClassVar[str] = "test only"

    def strength(self, bars: Bars) -> np.ndarray:
        return bars.close.copy()


def _cerebro():
    pytest.importorskip("backtrader")
    from tradescan.backtest.cerebro_portfolio import CerebroPortfolioEngine

    return CerebroPortfolioEngine()


@pytest.fixture(params=["vectorized", "cerebro"])
def engine(request):
    """Known-bar cases run on both portfolio engines, so the portfolio rules mean the same in each."""
    return VectorizedPortfolioEngine() if request.param == "vectorized" else _cerebro()


def _ticker(fire=(20,), scale=1.0, overrides=None, length=30):
    """Flat bars (O=C=100, H=101, L=99, so ATR=2) times `scale`, with selected bars replaced by (open, high, low,
    close) before scaling, and the signal firing on the bars in `fire`."""
    rows = [(overrides or {}).get(i, (100.0, 101.0, 99.0, 100.0)) for i in range(length)]
    frame = pd.DataFrame(
        rows, columns=["open", "high", "low", "close"], index=pd.bdate_range("2020-01-01", periods=length)
    )
    frame *= scale
    frame["volume"] = 1_000.0
    frame["fire"] = np.isin(np.arange(length), fire)
    return frame


def _run(engine, frames, portfolio, rules=BRACKET, priority=ClosePriority(), config=NO_COSTS, side=Direction.LONG):
    return engine.run(frames, ColumnSignal(side=side), config, rules, portfolio, priority)


# --- Allocation --------------------------------------------------------------------------------------


def _plan(size=100.0, reference=50.0) -> EntryPlan:
    return EntryPlan(OrderType.MARKET, math.nan, reference, reference - 2.0, 2.0, size, 1, 1.0)


def test_rank_puts_the_highest_score_first_then_the_watchlist_order_and_missing_scores_last():
    candidates = [
        Candidate(position, 0, score, _plan()) for position, score in enumerate([1.0, math.nan, 3.0, 1.0, math.nan])
    ]
    assert [candidate.ticker for candidate in rank(candidates)] == [2, 0, 3, 1, 4]


def test_allocate_shrinks_orders_to_the_exposure_cap_and_counts_what_it_skips():
    # 10_000 equity at a 50% cap is 5_000, of which 1_500 is used. Each plan is worth 100 * 20 = 2_000: the first
    # fits, the second is cut to the 1_500 left (75 shares), and nothing is left for the other two.
    candidates = [Candidate(position, 0, float(10 - position), _plan(100.0, 20.0)) for position in range(4)]
    cap = PortfolioConfig(max_positions=4, max_exposure_pct=50.0)
    allocation = allocate(candidates, slots_used=1, exposure=1_500.0, equity=10_000.0, portfolio=cap, lot_size=1.0)
    assert [(item.ticker, item.plan.size) for item in allocation.accepted] == [(0, 100.0), (1, 75.0)]
    assert (allocation.no_slot, allocation.no_room) == (0, 2)

    # With one slot used of two, only the first signal gets an order.
    slots = PortfolioConfig(max_positions=2, max_exposure_pct=100.0)
    allocation = allocate(candidates, slots_used=1, exposure=0.0, equity=10_000.0, portfolio=slots, lot_size=1.0)
    assert [item.ticker for item in allocation.accepted] == [0]
    assert (allocation.no_slot, allocation.no_room) == (3, 0)


def test_fit_keeps_whole_lots_under_the_room_left():
    plan = _plan(size=100.0, reference=20.0)
    assert fit(plan, 5_000.0, 1.0) is plan
    assert fit(plan, 1_010.0, 1.0).size == 50.0
    assert fit(plan, 1_010.0, 0.3).size == pytest.approx(50.4)
    assert fit(plan, 19.0, 1.0) is None
    assert fit(plan, -5.0, 1.0) is None


# --- Priority rules ----------------------------------------------------------------------------------


def _inputs(frames: dict[str, pd.DataFrame], direction: Direction = Direction.LONG) -> PriorityInputs:
    """What `prepare` hands a priority rule."""
    calendar = shared_calendar(frames.values())
    return PriorityInputs(
        tickers=tuple(frames),
        bars=tuple(Bars.from_frame(df, 14) for df in frames.values()),
        days=tuple(calendar.get_indexer(df.index) for df in frames.values()),
        calendar=calendar,
        direction=direction,
    )


def test_relative_strength_weighs_the_returns_over_each_lookback_and_mirrors_for_shorts():
    df = random_walk(400, seed=3)
    rule = RelativeStrengthPriority(periods=(20, 60), weights=(0.75, 0.25))
    close = df["close"]
    expected = (0.75 * (close / close.shift(20) - 1) + 0.25 * (close / close.shift(60) - 1)).to_numpy()
    np.testing.assert_allclose(rule.scores(_inputs({"X": df}))[0], expected, equal_nan=True)
    np.testing.assert_allclose(rule.scores(_inputs({"X": df}, Direction.SHORT))[0], -expected, equal_nan=True)
    assert np.isnan(expected[59])
    assert not np.isnan(expected[60])


def test_momentum_skips_the_latest_bars():
    df = random_walk(300, seed=4)
    (scores,) = MomentumPriority(lookback=100, skip=10).scores(_inputs({"X": df}))
    close = df["close"].to_numpy()
    assert scores[150] == pytest.approx(close[140] / close[50] - 1)
    assert np.isnan(scores[99])


def test_priority_rules_check_their_parameters():
    with pytest.raises(ValueError, match="lookbacks need as many weights"):
        RelativeStrengthPriority(periods=(10, 20), weights=(1.0,))
    with pytest.raises(ValueError, match="at least one weight"):
        RelativeStrengthPriority(periods=(10,), weights=(0.0,))
    with pytest.raises(ValueError, match="skip"):
        MomentumPriority(lookback=10, skip=10)
    assert priority_rules.names() == ["relative_strength", "momentum", "score"]
    assert priority_rules.create("momentum", {"lookback": 126, "skip": 0}) == MomentumPriority(lookback=126, skip=0)
    with pytest.raises(ValueError, match="lookback"):
        priority_rules.create("momentum", {"lookback": 5000})


# --- Score priority ----------------------------------------------------------------------------------

SCORER = Scorer(
    {"breakout": 1.5, "pattern": 0.5}, {"connors_rsi2_long": 2.0}, trend_bonus=1.0, weekly_bonus=0.5, rs_bonus=2.0,
    rs_strong_pct=60.0,
)  # fmt: skip


def _signals(direction: Direction) -> list[Signal]:
    return default_registry.select(directions={direction})


def _scan(frames, direction=Direction.LONG, scorer=SCORER, fresh_bars=5) -> ScanScore:
    return ScanScore.build(frames, _signals(direction), direction, scorer, ContextBuilder(), fresh_bars)


def _score(frames, direction=Direction.LONG, scorer=SCORER, fresh_bars=5) -> ScorePriority:
    return ScorePriority().with_scan(_scan(frames, direction, scorer, fresh_bars))


def test_the_context_at_every_bar_is_what_build_reports_on_the_history_up_to_it():
    builder = ContextBuilder(fast_period=20, slow_period=60, weekly_period=10)
    df = random_walk(500, seed=21)
    df = df[np.random.default_rng(2).random(len(df)) > 0.1]  # missing days, so some weeks are short
    close = df["close"]
    daily, weekly, strength = (
        builder.daily_trends(close),
        builder.weekly_trends(close),
        builder.relative_strengths(close),
    )
    sign = {Trend.UP: 1, Trend.DOWN: -1, Trend.NEUTRAL: 0}
    for bar in range(0, len(df), 5):
        context = builder.build("X", df.iloc[: bar + 1])
        assert (daily[bar], weekly[bar]) == (sign[context.daily_trend], sign[context.weekly_trend])
        np.testing.assert_equal(strength[bar], context.rs_raw)
    assert {-1, 0, 1} <= set(daily)
    assert {-1, 0, 1} <= set(weekly)


@pytest.mark.parametrize(
    ("direction", "traded"), [(Direction.LONG, "connors_rsi2_long"), (Direction.SHORT, "ema_cross_down")]
)
def test_the_score_priority_scores_like_the_scanner_on_the_history_up_to_each_close(direction, traded):
    frames = _random_frames(5, seed=800, bars=600)
    frames["T4"] = frames["T4"].iloc[200:]  # ranked once its relative strength has a year of bars
    setup = prepare(frames, default_registry.create(traded), COSTS, TradeRules(), _score(frames, direction))
    risk = RiskPlanner(100_000, 1, 25, 2, (2,))
    scanner = Scanner(_signals(direction), ContextBuilder(), SCORER, risk, fresh_bars=5, min_bars=1)
    calendar = shared_calendar(frames.values())
    checked = bonuses = 0
    for date in calendar[300::25]:
        for hit in scanner.scan({ticker: df.loc[:date] for ticker, df in frames.items()}).hits:
            ticker = setup.tickers[setup.names.index(hit.ticker)]
            assert hit.score.total == pytest.approx(ticker.scores[ticker.bars.dates.get_loc(date)], abs=1e-12)
            checked += 1
            bonuses += hit.score.relative_strength > 0 and hit.score.trend != 0 and hit.score.weekly != 0
    assert checked > 20
    assert bonuses > 3


def test_the_score_priority_ranks_relative_strength_among_the_tickers_with_a_bar_that_day():
    frames = _random_frames(3, seed=850, bars=400)
    gap = frames["T2"].index[300]
    frames["T2"] = frames["T2"].drop(gap)
    rs_only = Scorer({}, {}, trend_bonus=0.0, weekly_bonus=0.0, rs_bonus=1.0, rs_strong_pct=50.0)
    rule = ScorePriority().with_scan(ScanScore.build(frames, (), Direction.LONG, rs_only, ContextBuilder(), 3))
    scores = rule.scores(_inputs(frames))
    by_day = pd.DataFrame(
        {ticker: pd.Series(score, index=df.index) for (ticker, df), score in zip(frames.items(), scores, strict=True)}
    )
    assert (by_day.iloc[:252] == 0.0).all().all()  # no relative strength yet, no bonus
    ranked = by_day.iloc[252:]
    assert ranked.loc[gap, ["T0", "T1"]].tolist() == [1.0, 1.0]
    assert np.isnan(ranked.loc[gap, "T2"])
    assert (ranked.drop(gap).sum(axis=1) == 2.0).all()  # of three, the top two


def test_the_score_priority_reads_the_same_scores_on_a_shorter_history():
    frames = _random_frames(4, seed=900, bars=600)
    signal = default_registry.create("connors_rsi2_long")
    scan = ScanScore.build(frames, _signals(Direction.LONG), Direction.LONG, SCORER, ContextBuilder(), 3)
    early = {ticker: df.iloc[:400] for ticker, df in frames.items()}
    full = prepare(frames, signal, COSTS, TradeRules(), ScorePriority().with_scan(scan))
    shared = prepare(
        early, signal, COSTS, TradeRules(), ScorePriority().with_scan(scan)
    )  # how the in-sample run reads it
    own = prepare(early, signal, COSTS, TradeRules(), _score(early, fresh_bars=3))
    for whole, part, rebuilt in zip(full.tickers, shared.tickers, own.tickers, strict=True):
        np.testing.assert_array_equal(part.scores, whole.scores[:400])
        np.testing.assert_array_equal(rebuilt.scores, part.scores)
    assert len({float(score) for ticker in full.tickers for score in ticker.scores}) > 5


def test_the_score_priority_needs_the_scan_score_of_its_direction():
    frames = _random_frames(2, seed=950, bars=300)
    assert priority_rules.create("score") == ScorePriority()
    assert ScorePriority.needs_scan
    assert not RelativeStrengthPriority.needs_scan
    assert RelativeStrengthPriority().with_scan(_scan(frames)) == RelativeStrengthPriority()
    with pytest.raises(ValueError, match="needs the scanner's settings"):
        ScorePriority().scores(_inputs(frames))
    with pytest.raises(ValueError, match="holds short signals"):
        _score(frames, Direction.SHORT).scores(_inputs(frames))
    with pytest.raises(ValueError, match="no signal points for every bar of T1"):
        _score({"T0": frames["T0"]}).scores(_inputs(frames))


def test_the_portfolio_use_case_scores_with_the_runs_settings_and_every_signal_of_the_direction():
    frames = {name: random_walk(800, seed=seed) for seed, name in enumerate(["AAA", "BBB", "CCC", "SPY"], start=1)}
    overrides: dict[str, dict[str, Any]] = {
        "scoring": {"signal_weights": {"connors_rsi2_long": 3.0}},
        "trend": {"fast_period": 20},
        "scan": {"fresh_bars": 7},
    }
    setup = BacktestRequest(ticker="", signal="connors_rsi2_long", params={"oversold": 5.0}, settings=overrides)
    report = build_use_cases(Settings(), FakeProvider(frames)).portfolio.run(
        PortfolioRequest(Watchlist("demo", ("AAA", "BBB", "CCC"), "SPY"), setup, RuleChoice("score"))
    )
    scan, traded, settings = report.priority.scan, report.base.signal, report.base.settings
    assert report.priority.name == "score"
    assert scan.direction is Direction.LONG
    assert scan.scorer.weight(traded) == 3.0
    signals = [traded if signal.name == traded.name else signal for signal in _signals(Direction.LONG)]
    tickers = {ticker: frames[ticker] for ticker in ("AAA", "BBB", "CCC")}
    expected = ScanScore.build(
        tickers, signals, Direction.LONG, build_scorer(settings), build_context_builder(settings), 7
    )
    assert list(scan.signal_points) == list(tickers)
    for ticker in tickers:
        pd.testing.assert_series_equal(scan.signal_points[ticker], expected.signal_points[ticker])
    assert report.runs[0].result.trades
    # The report keeps what the score read, for the run's result to show.
    assert list(report.scan.settings) == ["scoring", "trend", "scan"]
    assert report.scan.settings["scan"] == {"fresh_bars": 7}
    assert report.scan.settings["scoring"]["signal_weights"] == {"connors_rsi2_long": 3.0}
    assert report.scan.settings["trend"]["fast_period"] == 20
    assert report.scan.signals == tuple(signal for signal in signals if signal is not traded)


def test_the_portfolio_use_case_reports_no_scan_inputs_for_a_priority_that_does_not_read_the_scanner():
    frames = {name: random_walk(400, seed=seed) for seed, name in enumerate(["AAA", "BBB", "SPY"], start=1)}
    setup = BacktestRequest(ticker="", signal="connors_rsi2_long")
    report = build_use_cases(Settings(), FakeProvider(frames)).portfolio.run(
        PortfolioRequest(Watchlist("demo", ("AAA", "BBB"), "SPY"), setup, RuleChoice("momentum"))
    )
    assert report.scan is None


def test_the_portfolio_use_case_scores_the_other_signals_with_the_runs_score_signal_params():
    frames = {name: random_walk(800, seed=seed) for seed, name in enumerate(["AAA", "BBB", "CCC", "SPY"], start=1)}
    setup = BacktestRequest(ticker="", signal="connors_rsi2_long", params={"oversold": 5.0})
    portfolio = build_use_cases(Settings(), FakeProvider(frames)).portfolio

    def scan(score_signal_params):
        request = PortfolioRequest(
            Watchlist("demo", ("AAA", "BBB", "CCC"), "SPY"), setup, RuleChoice("score"), score_signal_params
        )
        return portfolio.run(request).priority.scan

    # The traded signal's parameters come from the setup, so its entry changes nothing.
    params: dict[str, dict[str, Any]] = {"donchian_breakout": {"period": 5}, "connors_rsi2_long": {"oversold": 30.0}}
    overridden, defaults = scan(params), scan({})
    traded = default_registry.create("connors_rsi2_long", {"oversold": 5.0})
    signals = [
        traded if signal.name == traded.name else signal
        for signal in default_registry.select(directions={Direction.LONG}, params=params)
    ]
    tickers = {ticker: frames[ticker] for ticker in ("AAA", "BBB", "CCC")}
    expected = ScanScore.build(
        tickers, signals, Direction.LONG, overridden.scorer, overridden.context, Settings().scan.fresh_bars
    )
    for ticker in tickers:
        pd.testing.assert_series_equal(overridden.signal_points[ticker], expected.signal_points[ticker])
    assert any(not overridden.signal_points[ticker].equals(defaults.signal_points[ticker]) for ticker in tickers)


@pytest.mark.parametrize(
    ("priority", "params", "message"),
    [
        (RuleChoice("score"), {"nope": {"period": 5}}, "unknown signal"),
        (RuleChoice("score"), {"donchian_breakout": {"period": 1}}, "donchian_breakout.period must be between"),
        # checked even when nothing reads it
        (None, {"donchian_breakdown": {"period": 1}}, "donchian_breakdown.period must be between"),
    ],
)
def test_the_portfolio_use_case_refuses_bad_score_signal_params_before_loading_data(priority, params, message):
    provider = FakeProvider({"AAA": random_walk(300, seed=1), "SPY": random_walk(300, seed=2)})
    setup = BacktestRequest(ticker="", signal="connors_rsi2_long")
    with pytest.raises(ValueError, match=message):
        build_use_cases(Settings(), provider).portfolio.run(
            PortfolioRequest(Watchlist("demo", ("AAA",), "SPY"), setup, priority, params)
        )
    assert provider.calls == []


# --- Known bars on both portfolio engines ------------------------------------------------------------


def test_more_signals_than_slots_go_by_priority_then_watchlist_order(engine):
    frames = {"A": _ticker(), "B": _ticker(scale=2.0), "C": _ticker(scale=2.0)}
    one = _run(engine, frames, PortfolioConfig(max_positions=1))
    assert [item.ticker for item in one.trades] == ["B"]
    assert (one.orders, one.no_slot, one.no_room) == (1, 2, 0)
    assert one.trades[0].trade.size == 125  # risk 8 per share at twice the price: 1_000 / 8, worth 25% of equity

    two = _run(engine, frames, PortfolioConfig(max_positions=2))
    assert [item.ticker for item in two.trades] == ["B", "C"]
    assert two.no_slot == 1


def test_a_waiting_order_holds_its_slot_until_it_expires(engine):
    # A's buy-stop at 102 is never reached and expires at the close of bar 23, when B's second signal may trade.
    rules = TradeRules(entry=StopEntry(offset_atr=0.5, valid_bars=3), exits=(TargetExit(),))
    frames = {"A": _ticker(fire=(20,)), "B": _ticker(fire=(21, 23), overrides={24: (101.0, 103.0, 100.0, 102.0)})}
    result = _run(engine, frames, PortfolioConfig(max_positions=1), rules=rules)
    (item,) = result.trades
    dates = frames["B"].index
    assert (item.ticker, item.trade.signal_date, item.trade.entry_date, item.trade.entry_price) == (
        "B",
        dates[23],
        dates[24],
        102.0,
    )
    assert (result.orders, result.no_slot) == (2, 1)


def test_a_slot_frees_at_the_close_of_the_exit_bar(engine):
    frames = {"A": _ticker(fire=(20,)), "B": _ticker(fire=(24, 26))}
    result = _run(engine, frames, PortfolioConfig(max_positions=1))
    first, second = result.trades
    assert (first.ticker, first.trade.exit_reason, first.trade.exit_date) == (
        "A",
        ExitReason.TIME,
        frames["A"].index[26],
    )
    assert (second.ticker, second.trade.signal_date) == ("B", frames["B"].index[26])
    assert result.no_slot == 1


def test_orders_shrink_to_the_exposure_cap(engine):
    frames = {name: _ticker() for name in "ABC"}
    result = _run(engine, frames, PortfolioConfig(max_positions=5, max_exposure_pct=40.0))
    assert [(item.ticker, item.trade.size) for item in result.trades] == [("A", 250), ("B", 150)]
    assert (result.orders, result.no_room) == (2, 1)
    assert result.exposure_pct.iloc[21] == pytest.approx(40.0)


def test_sizes_come_from_the_shared_equity_marked_to_market(engine):
    # A's 250 shares gain 20 by the close of bar 22, so B's signal there is sized from 105_000: 262 shares.
    frames = {"A": _ticker(fire=(20,), overrides={22: (100.0, 121.0, 99.0, 120.0)}), "B": _ticker(fire=(22,))}
    result = _run(engine, frames, PortfolioConfig(max_positions=5), rules=TradeRules(exits=()))
    assert result.equity.iloc[22] == pytest.approx(105_000.0)
    assert [(item.ticker, item.trade.size) for item in result.trades] == [("A", 250), ("B", 262)]
    assert list(result.positions.iloc[20:24]) == [0, 1, 1, 2]


def test_a_ticker_whose_bars_end_early_keeps_its_open_position_and_slot(engine):
    frames = {"A": _ticker(fire=(20,), length=25), "B": _ticker(fire=(27,))}
    result = _run(engine, frames, PortfolioConfig(max_positions=1), rules=TradeRules(exits=()))
    (item,) = result.trades
    assert (item.ticker, item.trade.exit_reason, item.trade.exit_date) == ("A", ExitReason.OPEN, frames["A"].index[-1])
    assert result.equity.index.equals(frames["B"].index)
    assert (result.positions.iloc[21:] == 1).all()
    assert result.no_slot == 1


def test_one_ticker_trades_like_a_single_ticker_backtest():
    df = random_walk(1500, seed=11)
    signal = default_registry.create("connors_rsi2_long")
    config = BacktestConfig(commission_pct=0.1, slippage_pct=0.05)
    single = VectorizedEngine().run("RW", df, signal, config, TradeRules())
    portfolio = VectorizedPortfolioEngine().run(
        {"RW": df}, signal, config, TradeRules(), PortfolioConfig(1), ClosePriority()
    )
    assert len(portfolio.trades) == len(single.trades) > 10
    for item, trade in zip(portfolio.trades, single.trades, strict=True):
        assert (item.trade.entry_date, item.trade.exit_date, item.trade.size) == (
            trade.entry_date,
            trade.exit_date,
            trade.size,
        )
        assert item.trade.pnl == pytest.approx(trade.pnl, rel=1e-9)
    np.testing.assert_allclose(portfolio.equity.to_numpy(), single.equity.to_numpy(), rtol=1e-9)


# --- Both portfolio engines give identical results ---------------------------------------------------


def _random_frames(count: int, seed: int, bars: int = 1000) -> dict[str, pd.DataFrame]:
    return {f"T{i}": random_walk(bars, seed=seed + i) for i in range(count)}


def _ragged_frames() -> dict[str, pd.DataFrame]:
    """Tickers that start later, end earlier and miss random days."""
    frames = _random_frames(6, seed=300)
    rng = np.random.default_rng(5)
    frames["T1"] = frames["T1"].iloc[250:]
    frames["T2"] = frames["T2"].iloc[:800]
    frames["T3"] = frames["T3"][rng.random(len(frames["T3"])) > 0.05]
    return frames


def _gappy_frames() -> dict[str, pd.DataFrame]:
    """Every ticker misses about a third of the days, so orders often wait while other tickers move on."""
    frames = _random_frames(4, seed=400)
    return {name: df[np.random.default_rng(i).random(len(df)) > 0.3] for i, (name, df) in enumerate(frames.items())}


COSTS = BacktestConfig(commission_pct=0.1, slippage_pct=0.05)


def _score_case():
    """The score priority ranks within the watchlist, so its scores come from every ticker at once."""
    frames = _random_frames(6, 200)
    return frames, "connors_rsi2_long", TradeRules(), PortfolioConfig(2), _score(frames, fresh_bars=3)


PARITY_CASES = {
    "rsi2_relative_strength": (
        _random_frames(6, 200), "connors_rsi2_long", TradeRules(), PortfolioConfig(3), RelativeStrengthPriority(),
    ),
    "breakout_stop_entry_momentum": (
        _random_frames(6, 200), "donchian_breakout",
        TradeRules(StopEntry(valid_bars=3), (TrailingStop(), TargetExit(target_r=3.0))),
        PortfolioConfig(2, 60.0), MomentumPriority(),
    ),
    "short_limit_entry": (
        _random_frames(6, 200), "ema_cross_down", TradeRules(entry=LimitEntry(valid_bars=2)), PortfolioConfig(4, 80.0),
        RelativeStrengthPriority(),
    ),
    "exposure_cap": (
        _random_frames(6, 200), "connors_rsi2_long", TradeRules(), PortfolioConfig(5, 30.0), MomentumPriority(),
    ),
    "ragged_calendars": (
        _ragged_frames(), "donchian_breakout",
        TradeRules(StopEntry(valid_bars=3), (TrailingStop(), TimeExit(max_hold_bars=30))),
        PortfolioConfig(2, 70.0), MomentumPriority(),
    ),
    "gappy_calendars_limit_entry": (
        _gappy_frames(), "connors_rsi2_long", TradeRules(entry=LimitEntry(offset_atr=0.1)), PortfolioConfig(4),
        RelativeStrengthPriority(),
    ),
    "filters_with_benchmark": (
        _random_frames(5, 500), "donchian_breakout",
        TradeRules(filters=(TrendFilter(period=100), MarketFilter(period=100))).with_benchmark(
            random_walk(1100, seed=9)["close"]
        ),
        PortfolioConfig(3), RelativeStrengthPriority(),
    ),
    "score_priority": _score_case(),
}  # fmt: skip


@pytest.mark.parametrize("case", PARITY_CASES.values(), ids=PARITY_CASES.keys())
def test_portfolio_engines_match(case):
    frames, signal_name, rules, portfolio, priority = case
    signal = default_registry.create(signal_name)
    fast = VectorizedPortfolioEngine().run(frames, signal, COSTS, rules, portfolio, priority)
    slow = _cerebro().run(frames, signal, COSTS, rules, portfolio, priority)
    assert len(fast.trades) == len(slow.trades) > 20
    for left, right in zip(fast.trades, slow.trades, strict=True):
        a, b = left.trade, right.trade
        assert (left.ticker, a.signal_date, a.entry_date, a.exit_date, a.exit_reason, a.size) == (
            right.ticker, b.signal_date, b.entry_date, b.exit_date, b.exit_reason, b.size
        )  # fmt: skip
        assert a.entry_price == pytest.approx(b.entry_price, rel=1e-9)
        assert a.exit_price == pytest.approx(b.exit_price, rel=1e-9)
        assert a.pnl == pytest.approx(b.pnl, rel=1e-6, abs=1e-6)
    assert fast.equity.index.equals(slow.equity.index)
    assert fast.equity.index.equals(shared_calendar(frames.values()))
    np.testing.assert_allclose(fast.equity.to_numpy(), slow.equity.to_numpy(), rtol=1e-9)
    np.testing.assert_array_equal(fast.positions.to_numpy(), slow.positions.to_numpy())
    np.testing.assert_allclose(fast.exposure_pct.to_numpy(), slow.exposure_pct.to_numpy(), rtol=1e-9)
    assert (fast.orders, fast.no_slot, fast.no_room) == (slow.orders, slow.no_slot, slow.no_room)
    assert fast.positions.max() <= portfolio.max_positions


def test_the_parity_cases_exercise_both_caps():
    signal = default_registry.create("connors_rsi2_long")
    frames, _, rules, portfolio, priority = PARITY_CASES["exposure_cap"]
    assert VectorizedPortfolioEngine().run(frames, signal, COSTS, rules, portfolio, priority).no_room > 0
    for case in ("rsi2_relative_strength", "score_priority"):
        frames, _, rules, portfolio, priority = PARITY_CASES[case]
        assert VectorizedPortfolioEngine().run(frames, signal, COSTS, rules, portfolio, priority).no_slot > 0


# --- Periods and metrics -----------------------------------------------------------------------------


def test_periods_split_the_shared_calendar():
    frames = _ragged_frames()
    calendar = shared_calendar(frames.values())
    split = split_history(calendar, 30.0)
    start = split.out_of_sample[0]
    frames["late"] = random_walk(1000, seed=1).loc[start:]  # only has out-of-sample bars
    signal = default_registry.create("connors_rsi2_long")
    periods = run_portfolio_periods(
        VectorizedPortfolioEngine(),
        frames,
        signal,
        COSTS,
        TradeRules(),
        PortfolioConfig(3),
        RelativeStrengthPriority(),
        start,
    )
    early, late = periods.in_sample, periods.out_of_sample
    assert early.equity.index[-1] < start
    assert "late" not in early.tickers
    assert early.trades
    assert all(item.trade.exit_date < start for item in early.trades)
    assert late.equity.index[0] == calendar[0]
    assert "late" in late.tickers
    assert late.trades
    assert all(item.trade.signal_date >= start for item in late.trades)
    assert (late.equity.loc[: calendar[split.index - 1]] == COSTS.initial_equity).all()


def test_portfolio_metrics_use_the_benchmark_and_the_days_with_a_position():
    frames = _random_frames(4, seed=600)
    signal = default_registry.create("connors_rsi2_long")
    result = VectorizedPortfolioEngine().run(
        frames, signal, COSTS, TradeRules(), PortfolioConfig(2), MomentumPriority()
    )
    benchmark = random_walk(1200, seed=8)["close"]
    full = portfolio_metrics(result, benchmark, 252)
    assert full.metrics.buy_hold_pct == pytest.approx((benchmark.iloc[999] / benchmark.iloc[0] - 1) * 100)
    assert full.metrics.exposure_pct == pytest.approx((result.positions > 0).mean() * 100)
    assert full.metrics.trades == sum(item.trade.is_closed for item in result.trades)
    assert full.stats.max_positions == 2
    assert full.stats.average_positions == pytest.approx(result.positions.mean())
    assert (full.stats.orders, full.stats.skipped_no_slot) == (result.orders, result.no_slot)

    start = result.equity.index[700]
    late = portfolio_metrics(result, benchmark, 252, start)
    assert late.metrics.total_return_pct == pytest.approx((result.equity.iloc[-1] / result.equity.iloc[700] - 1) * 100)
    assert late.metrics.buy_hold_pct == pytest.approx((benchmark.iloc[999] / benchmark.iloc[700] - 1) * 100)

    without = portfolio_metrics(result, benchmark.iloc[:0], 252)
    assert math.isnan(without.metrics.buy_hold_pct)


def test_contributions_add_up_to_the_portfolio_result():
    frames = _random_frames(5, seed=700)
    frames["idle"] = random_walk(1000, seed=1).iloc[:50]  # too short to trade
    signal = default_registry.create("connors_rsi2_long")
    result = VectorizedPortfolioEngine().run(
        frames, signal, COSTS, TradeRules(), PortfolioConfig(3), MomentumPriority()
    )
    rows = contributions(result, COSTS.initial_equity)
    assert [row.ticker for row in rows] == list(frames)
    assert sum(row.pnl for row in rows) == pytest.approx(result.equity.iloc[-1] - COSTS.initial_equity)
    assert sum(row.contribution_pct for row in rows) == pytest.approx(
        result.equity.iloc[-1] / COSTS.initial_equity * 100 - 100
    )
    idle = rows[-1]
    assert (idle.trades, idle.pnl) == (0, 0.0)
    assert math.isnan(idle.win_rate_pct)
