"""Event-driven reference for the portfolio backtest with backtrader's Cerebro (optional: `pip install -e .[cerebro]`).

Every ticker is a data feed of one strategy and trades with the single-ticker Cerebro engine's orders
(`cerebro.TickerOrders`). Signals, rule levels and priority scores come from `portfolio.prepare`, and every close
allocates with `allocation.allocate`, so only the order execution differs from the vectorized engine. Two
changes to backtrader's broker keep it comparable:

* cash never limits a fill: the commission scheme's leverage is so high that a purchase takes almost no cash.
  Leverage leaves the portfolio value (`getvalue`) unchanged, so the exposure cap is the only limit on size;
* an order is only tried on a bar of its ticker after the bar it was placed on. Feeds on different dates move
  separately, and backtrader would otherwise try an order placed at a close against that same bar whenever
  another ticker moves on and the order's ticker does not.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

try:
    import backtrader as bt
except ImportError as error:  # pragma: no cover - depends on the optional extra
    raise ImportError("The cerebro engine needs backtrader: pip install -e .[cerebro]") from error

from tradescan.backtest.allocation import Candidate, PortfolioConfig, allocate
from tradescan.backtest.base import BacktestConfig
from tradescan.backtest.cerebro import LEVERAGE, TickerOrders
from tradescan.backtest.portfolio import PortfolioResult, PortfolioSetup, PortfolioTrade, prepare
from tradescan.backtest.priority import PriorityRule
from tradescan.backtest.trade_rules import TradeRules
from tradescan.data.schema import OHLCV_COLUMNS
from tradescan.signals.base import Signal


class _Broker(bt.brokers.BackBroker):
    def _try_exec(self, order: bt.Order) -> None:
        if order.data.datetime[0] <= order.created.dt:
            return  # the order's ticker has no bar after the one the order was placed on yet
        super()._try_exec(order)


class _PortfolioStrategy(bt.Strategy):
    params = (("setup", None), ("config", BacktestConfig()), ("portfolio", PortfolioConfig()))

    def __init__(self) -> None:
        setup: PortfolioSetup = self.p.setup
        self._tickers = [
            TickerOrders(self, data, ticker.rules, setup.direction) for data, ticker in zip(self.datas, setup.tickers)
        ]
        self._by_name = {data._name: orders for data, orders in zip(self.datas, self._tickers)}
        self._lengths = [0] * len(self.datas)
        self.dates: list[pd.Timestamp] = []
        self.equity_values: list[float] = []
        self.open_positions: list[int] = []
        self.exposure: list[float] = []
        self.orders = self.no_slot = self.no_room = 0

    def prenext(self) -> None:
        self.next()  # tickers whose bars start later have none yet

    def next(self) -> None:
        moved = [position for position, data in enumerate(self.datas) if len(data) > self._lengths[position]]
        if not moved:
            return
        for position in moved:
            self._lengths[position] = len(self.datas[position])
        self.dates.append(pd.Timestamp(self.datas[moved[0]].datetime.datetime(0)))
        equity = self.broker.getvalue()
        self.equity_values.append(equity)
        for position in moved:
            self._tickers[position].update(self._lengths[position] - 1)

        open_value = waiting_value = 0.0
        open_positions = busy = 0
        for data, orders in zip(self.datas, self._tickers):
            if orders.position:
                open_value += abs(orders.position.size) * data.close[0]
                open_positions += 1
            elif (plan := orders.waiting) is not None:
                waiting_value += plan.size * plan.reference
            busy += not orders.free
        self.open_positions.append(open_positions)
        self.exposure.append(open_value / equity * 100.0 if equity > 0 else np.nan)

        setup: PortfolioSetup = self.p.setup
        config: BacktestConfig = self.p.config
        candidates = []
        for position in moved:
            ticker, index = setup.tickers[position], self._lengths[position] - 1
            if not self._tickers[position].free or not ticker.events[index] or index + 1 >= len(ticker.bars):
                continue
            plan = ticker.rules.plan(index, equity, config)
            if plan is not None:
                candidates.append(Candidate(position, index, float(ticker.scores[index]), plan))
        allocation = allocate(candidates, busy, open_value + waiting_value, equity, self.p.portfolio, config.lot_size)
        self.orders += len(allocation.accepted)
        self.no_slot += allocation.no_slot
        self.no_room += allocation.no_room
        for candidate in allocation.accepted:
            self._tickers[candidate.ticker].submit_entry(candidate.index, candidate.plan)

    def notify_order(self, order: bt.Order) -> None:
        self._by_name[order.data._name].notify_order(order)

    def stop(self) -> None:
        for orders in self._tickers:
            orders.finish()

    def portfolio_trades(self) -> list[PortfolioTrade]:
        return [PortfolioTrade(name, trade) for name, orders in self._by_name.items() for trade in orders.trades]


class CerebroPortfolioEngine:
    name = "cerebro"

    def run(
        self,
        frames: Mapping[str, pd.DataFrame],
        signal: Signal,
        config: BacktestConfig,
        rules: TradeRules,
        portfolio: PortfolioConfig,
        priority: PriorityRule,
    ) -> PortfolioResult:
        setup = prepare(frames, signal, config, rules, priority)
        cerebro = bt.Cerebro(stdstats=False)
        cerebro.setbroker(_Broker())
        for ticker, df in frames.items():
            cerebro.adddata(bt.feeds.PandasData(dataname=df.loc[:, list(OHLCV_COLUMNS)], openinterest=None), name=ticker)
        cerebro.addstrategy(_PortfolioStrategy, setup=setup, config=config, portfolio=portfolio)
        cerebro.broker.setcash(config.initial_equity)
        cerebro.broker.setcommission(commission=config.commission_pct / 100.0, leverage=LEVERAGE)
        cerebro.broker.set_slippage_perc(config.slippage_pct / 100.0)
        strategy = cerebro.run()[0]

        dates = pd.DatetimeIndex(strategy.dates, name="date")
        return PortfolioResult(
            engine=self.name,
            signal=signal.name,
            tickers=setup.names,
            equity=pd.Series(strategy.equity_values, index=dates, name="equity"),
            positions=pd.Series(strategy.open_positions, index=dates, name="positions"),
            exposure_pct=pd.Series(strategy.exposure, index=dates, name="exposure_pct"),
            trades=setup.ordered(strategy.portfolio_trades()),
            orders=strategy.orders,
            no_slot=strategy.no_slot,
            no_room=strategy.no_room,
        )
