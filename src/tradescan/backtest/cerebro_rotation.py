"""Event-driven reference for the momentum rotation with backtrader's Cerebro (optional: `pip install -e .[cerebro]`).

Every ticker, and the safe asset when it is not in the watchlist, is a data feed of one strategy. Rankings, weights
and absolute momentum come from `rotation.prepare`, each rebalance picks with `rotation.targets` and sizes its orders
with `rotation.rebalance_orders` from the broker's portfolio value, so only the order execution differs from the
vectorized engine: market orders for the share differences, filled by backtrader's broker with the portfolio
engine's two changes. Cash never limits a fill (the commission scheme's leverage is so high that a purchase takes
almost no cash), and an order is only tried on a bar of its ticker after the bar it was placed on
(`cerebro.MultiFeedBroker`). An order that still waits at the next rebalance is cancelled, as the vectorized engine
drops an order whose ticker has no bar before it.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

try:
    import backtrader as bt
except ImportError as error:  # pragma: no cover - depends on the optional extra
    raise ImportError("The cerebro engine needs backtrader: pip install -e .[cerebro]") from error

from tradescan.backtest.base import BacktestConfig
from tradescan.backtest.cerebro import LEVERAGE, MultiFeedBroker
from tradescan.backtest.portfolio import PortfolioTrade
from tradescan.backtest.priority import PriorityRule
from tradescan.backtest.rotation import (
    EPSILON,
    Holding,
    RotationConfig,
    RotationResult,
    RotationSetup,
    percent_of_equity,
    prepare,
    rebalance_days,
    rebalance_orders,
    start_day,
    targets,
)
from tradescan.backtest.weighting import WeightRule
from tradescan.data.schema import OHLCV_COLUMNS


class _RotationStrategy(bt.Strategy):
    params = (("setup", None), ("config", BacktestConfig()), ("rotation", RotationConfig()), ("start", None))

    def __init__(self) -> None:
        setup: RotationSetup = self.p.setup
        self._rebalance_days = set(rebalance_days(setup.calendar, self.p.rotation.rebalance, self.p.start).tolist())
        self._bars = 0  # bars of every feed so far
        self._waiting: dict[int, tuple[bt.Order, int, pd.Timestamp]] = {}  # by ref: the order, its asset, its rebalance
        self._holdings: dict[int, Holding] = {}  # by asset position
        self.trades: list[PortfolioTrade] = []
        self.dates: list[pd.Timestamp] = []
        self.equity_values: list[float] = []
        self.holdings: list[int] = []
        self.gross_values: list[float] = []
        self.safe_values: list[float] = []
        self.first: int | None = None  # the calendar day of the first rebalance with a pick
        self.rebalances = self.orders = self.unfilled = 0
        self.traded_value = self.commissions = 0.0

    def prenext(self) -> None:
        self.next()  # tickers whose bars start later have none yet

    def next(self) -> None:
        bars = sum(len(data) for data in self.datas)
        if bars == self._bars:
            return
        self._bars = bars
        day = len(self.dates)
        self.dates.append(max(pd.Timestamp(data.datetime.datetime(0)) for data in self.datas if len(data)))
        equity = self.broker.getvalue()
        held = np.array([self.getposition(data).size for data in self.datas], dtype=float)
        values = np.array(
            [size * data.close[0] if len(data) else 0.0 for size, data in zip(held, self.datas, strict=True)]
        )
        safe = self.p.setup.safe
        self.equity_values.append(equity)
        self.holdings.append(int(np.count_nonzero(np.abs(held) > EPSILON)))
        self.gross_values.append(float(np.abs(values).sum()))
        self.safe_values.append(float(values[safe]) if safe is not None else 0.0)
        if day in self._rebalance_days:
            self._rebalance(day, held, equity)

    def _rebalance(self, day: int, held: np.ndarray, equity: float) -> None:
        for order, _, _ in self._waiting.values():
            self.cancel(order)  # its ticker had no bar since the last rebalance
            self.unfilled += 1
        self._waiting.clear()
        setup: RotationSetup = self.p.setup
        chosen = targets(setup, self.p.rotation, day)
        if self.first is None and not chosen.picks:
            return  # the lookbacks are still warming up
        self.first = day if self.first is None else self.first
        self.rebalances += 1
        for position, shares in rebalance_orders(setup, chosen, day, held, equity, self.p.config.lot_size).items():
            place = self.buy if shares > 0 else self.sell
            order = place(data=self.datas[position], size=abs(shares), exectype=bt.Order.Market)
            self._waiting[order.ref] = (order, position, setup.calendar[day])

    def notify_order(self, order: bt.Order) -> None:
        if order.status in (order.Submitted, order.Accepted):
            return
        waiting = self._waiting.pop(order.ref, None)
        if waiting is None or order.status != order.Completed:
            return
        _, position, rebalance = waiting
        executed = order.executed
        date = pd.Timestamp(bt.num2date(executed.dt))
        self.orders += 1
        self.traded_value += abs(executed.size) * executed.price
        self.commissions += executed.comm
        holding = self._holdings.get(position)
        if holding is None:
            holding = self._holdings[position] = Holding(rebalance, date)
        holding.fill(executed.size, executed.price, executed.comm)
        if holding.empty:
            self.trades.append(PortfolioTrade(self.datas[position]._name, holding.trade(date)))
            del self._holdings[position]

    def stop(self) -> None:
        """At the end of the run: a holding still open is marked to its ticker's last close."""
        for position, holding in self._holdings.items():
            data = self.datas[position]
            last = pd.Timestamp(data.datetime.datetime(0))
            self.trades.append(PortfolioTrade(data._name, holding.trade(last, data.close[0])))


class CerebroRotationEngine:
    name = "cerebro"

    def run(
        self,
        frames: Mapping[str, pd.DataFrame],
        config: BacktestConfig,
        rotation: RotationConfig,
        ranking: PriorityRule,
        weighting: WeightRule,
        safe_frame: pd.DataFrame | None = None,
        start: pd.Timestamp | None = None,
    ) -> RotationResult:
        setup = prepare(frames, config, rotation, ranking, weighting, safe_frame)
        extra = {rotation.safe_asset: safe_frame} if rotation.safe_asset and safe_frame is not None else {}
        sources = {**extra, **frames}
        cerebro = bt.Cerebro(stdstats=False)
        cerebro.setbroker(MultiFeedBroker())
        for name in setup.names:
            cerebro.adddata(
                bt.feeds.PandasData(dataname=sources[name].loc[:, list(OHLCV_COLUMNS)], openinterest=None), name=name
            )
        cerebro.addstrategy(_RotationStrategy, setup=setup, config=config, rotation=rotation, start=start)
        cerebro.broker.setcash(config.initial_equity)
        cerebro.broker.setcommission(commission=config.commission_pct / 100.0, leverage=LEVERAGE)
        cerebro.broker.set_slippage_perc(config.slippage_pct / 100.0)
        strategy = cerebro.run()[0]

        dates = pd.DatetimeIndex(strategy.dates, name="date")
        begin = start_day(dates, strategy.first, start)
        index = dates[begin:]
        equity = np.array(strategy.equity_values)
        exposure = percent_of_equity(np.array(strategy.gross_values), equity)
        safe_pct = percent_of_equity(np.array(strategy.safe_values), equity)
        return RotationResult(
            engine=self.name,
            tickers=setup.names,
            equity=pd.Series(equity[begin:], index=index, name="equity"),
            holdings=pd.Series(np.array(strategy.holdings)[begin:], index=index, name="holdings"),
            exposure_pct=pd.Series(exposure[begin:], index=index, name="exposure_pct"),
            safe_pct=pd.Series(safe_pct[begin:], index=index, name="safe_pct"),
            trades=setup.ordered(strategy.trades),
            rebalances=strategy.rebalances,
            orders=strategy.orders,
            unfilled=strategy.unfilled,
            traded_value=strategy.traded_value,
            commissions=strategy.commissions,
            targets=targets(setup, rotation, len(setup.calendar) - 1),
        )
