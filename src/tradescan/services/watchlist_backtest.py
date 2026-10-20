"""Watchlist backtest: one setup run separately on every ticker of a watchlist."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, fields, replace

import pandas as pd

from tradescan.backtest.metrics import Metrics
from tradescan.backtest.pooled import BREAK_EVEN, PooledTrades, Spread, pool_trades, spread
from tradescan.backtest.tickers import Period, PeriodRun, TickerJob, TickerRun
from tradescan.backtest.trade_rules import RuleCatalog, default_catalog
from tradescan.config import Settings
from tradescan.parallel import TaskRunner
from tradescan.services.backtest import BacktestRequest, ResolvedBacktest, resolve_backtest, rules_with_benchmark
from tradescan.services.market_data import MarketData
from tradescan.signals.registry import SignalRegistry
from tradescan.watchlist import Watchlist


@dataclass(frozen=True)
class WatchlistBacktestRequest:
    """`setup` runs on every ticker of `universe`. Its `ticker` and `engines` are ignored: every ticker runs
    on the vectorized engine. Without a benchmark of its own, the setup takes the watchlist's."""

    universe: Watchlist
    setup: BacktestRequest


@dataclass(frozen=True)
class TickerRow:
    ticker: str
    start: pd.Timestamp
    end: pd.Timestamp
    run: TickerRun


@dataclass(frozen=True)
class PeriodSummary:
    tickers: int  # tickers that have this period
    pooled: PooledTrades  # every ticker's closed trades together
    spreads: dict[str, Spread]  # by metric name: how the tickers' values are spread


@dataclass(frozen=True)
class WatchlistBacktestReport:
    universe: Watchlist
    base: ResolvedBacktest
    rows: list[TickerRow]  # in watchlist order
    periods: dict[Period, PeriodSummary]
    missing: list[str]


METRIC_NAMES = tuple(item.name for item in fields(Metrics))


class WatchlistBacktestUseCase:
    def __init__(
        self,
        market_data: MarketData,
        settings: Settings,
        registry: SignalRegistry,
        runner: TaskRunner,
        rules: RuleCatalog = default_catalog,
    ) -> None:
        self._market_data = market_data
        self._settings = settings
        self._registry = registry
        self._runner = runner
        self._rules = rules

    def run(self, request: WatchlistBacktestRequest) -> WatchlistBacktestReport:
        universe = request.universe
        setup = replace(request.setup, benchmark=request.setup.benchmark or universe.benchmark)
        base = resolve_backtest(setup, self._settings, self._registry, self._rules)
        history = setup.period or base.settings.backtest.period
        tickers = list(universe.tickers)
        loaded = self._market_data.load(
            [*tickers, base.benchmark] if base.benchmark else tickers, history, setup.interval
        )
        rules = rules_with_benchmark(base, loaded)
        frames = [(ticker, loaded.frames[ticker]) for ticker in tickers if ticker in loaded.frames]
        if not frames:
            raise ValueError(f"No data for any ticker of {universe.name}")

        runs = self._runner.map(TickerJob(base.signal, rules, base.config), frames)
        rows = [
            TickerRow(ticker, df.index[0], df.index[-1], run) for (ticker, df), run in zip(frames, runs, strict=True)
        ]
        return WatchlistBacktestReport(
            universe=universe,
            base=base,
            rows=rows,
            periods={period: _summary([row.run.period(period) for row in rows]) for period in Period},
            missing=[ticker for ticker in loaded.missing if ticker in tickers],
        )


def _summary(runs: Sequence[PeriodRun | None]) -> PeriodSummary:
    """Pooled trades and the spread of every metric over the tickers that have this period."""
    present = [run for run in runs if run is not None]
    return PeriodSummary(
        tickers=len(present),
        pooled=pool_trades(run.r_multiples for run in present),
        spreads={
            name: spread((getattr(run.metrics, name) for run in present), BREAK_EVEN.get(name)) for name in METRIC_NAMES
        },
    )
