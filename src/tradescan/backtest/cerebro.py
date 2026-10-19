"""Event-driven validation with backtrader's Cerebro (optional: `pip install -e .[cerebro]`).

Signals and rule levels are precomputed by the same code the pandas engine uses and read by bar
index, so every rule is defined once. Cerebro adds realistic order handling: real market, stop and
limit orders, the stop and target linked as one-cancels-other, percentage commission and slippage.

As in the vectorized engine, cash never limits a fill: the commission scheme's leverage is so high that a
purchase takes almost no cash, which leaves the portfolio value (`getvalue`) unchanged. A pyramided position can
hold several units of up to `max_position_pct` of equity each.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

try:
    import backtrader as bt
except ImportError as error:  # pragma: no cover - depends on the optional extra
    raise ImportError("The cerebro engine needs backtrader: pip install -e .[cerebro]") from error

from tradescan.backtest.base import BacktestConfig, BacktestResult, ExitReason, Fill, Trade
from tradescan.backtest.entries import OrderType
from tradescan.backtest.exits import ExitOrders, ExitTracker, OpenTrade
from tradescan.backtest.pyramid import Pyramiding, Units
from tradescan.backtest.rules import Bars
from tradescan.backtest.trade_rules import EntryPlan, PreparedRules, TradeRules
from tradescan.data.schema import OHLCV_COLUMNS
from tradescan.signals.base import Direction, Signal

_EXEC_TYPES = {OrderType.MARKET: bt.Order.Market, OrderType.STOP: bt.Order.Stop, OrderType.LIMIT: bt.Order.Limit}
LEVERAGE = 1e9  # buying takes 1e-9 of the price in cash, so cash never runs out


class TickerOrders:
    """One ticker's entry order, exit orders and trades inside a backtrader strategy, which may trade other
    tickers too: the strategy calls `update` at every close of the ticker and forwards its order notifications.

    Notifications carry clones of orders, so orders are matched by `ref`, never by identity.

    With pyramiding, the stop order for the next unit is submitted after the exit orders and linked to them as one
    one-cancels-other group. The broker tries orders in the order they were submitted, so an exit on a bar cancels
    that bar's add, and an add cancels the exit orders only after they were tried; they are then submitted again at
    the close, for the new size.
    """

    def __init__(
        self,
        strategy: bt.Strategy,
        data: bt.AbstractDataBase,
        rules: PreparedRules,
        direction: Direction,
        pyramid: Pyramiding = Pyramiding(),
    ) -> None:
        self._strategy = strategy
        self._data = data
        self._rules = rules
        self._direction = direction
        self._pyramid = pyramid
        self.trades: list[Trade] = []
        self._reset()

    def _reset(self) -> None:
        self._entry_order = None
        self._plan: EntryPlan | None = None
        self._signal: tuple[int, pd.Timestamp] | None = None  # (bar index, date)
        self._fills: list[tuple[pd.Timestamp, float, float, float]] = []  # (date, price, size, commission) per unit
        self._tracker: ExitTracker | None = None
        self._units: Units | None = None
        self._exit_orders: list[Any] = []  # backtrader orders
        self._exit_reasons: dict[int, str] = {}
        self._add_order: Any = None  # a backtrader order
        # The levels and reasons of the live exit orders, the add level and the size.
        self._levels: tuple[object, ...] | None = None
        self._closing = False

    @property
    def position(self) -> bt.Position:
        return self._strategy.getposition(self._data)

    @property
    def free(self) -> bool:
        """No entry order waits and no position is open, so a signal may place an order."""
        return self._entry_order is None and not self.position

    @property
    def waiting(self) -> EntryPlan | None:
        """The plan of the entry order that waits to fill; None without one."""
        return self._plan if self._entry_order is not None and not self.position else None

    def _index(self) -> int:
        return len(self._data) - 1

    def update(self, index: int) -> None:
        """At the close of bar `index`: move the exit orders of an open position, or cancel an expired entry order
        (a signal on the bar it expires may place a new one)."""
        if self.position:
            self._manage_exits(index)
            return
        if self._entry_order is not None:
            assert self._plan is not None
            assert self._signal is not None
            if index - self._signal[0] < self._plan.valid_bars:
                return
            self._strategy.cancel(self._entry_order)
            self._reset()

    def submit_entry(self, index: int, plan: EntryPlan) -> None:
        order = self._strategy.buy if self._direction is Direction.LONG else self._strategy.sell
        price = None if plan.type is OrderType.MARKET else plan.level
        self._entry_order = order(data=self._data, size=plan.size, exectype=_EXEC_TYPES[plan.type], price=price)
        self._plan = plan
        self._signal = (index, pd.Timestamp(self._data.datetime.datetime(0)))

    def _manage_exits(self, index: int) -> None:
        if self._closing:
            return
        assert self._tracker is not None
        orders: ExitOrders = self._tracker.orders(index)
        if orders.at_open is not None:
            self._cancel_exits()
            self._exit_reasons[self._strategy.close(data=self._data).ref] = orders.at_open
            self._closing = True
            return
        add = self._units.add_level() if self._units is not None else None
        levels = (orders.stop, orders.stop_reason, orders.target, orders.target_reason, add, abs(self.position.size))
        if levels != self._levels:
            self._cancel_exits()
            self._submit_exits(orders, add)
            self._levels = levels

    def _submit_exits(self, orders: ExitOrders, add: float | None) -> None:
        """The stop first, so it is checked first on a bar that touches both, the target linked to it, and last the
        stop order for the next unit, linked to both."""
        size = abs(self.position.size)
        long = self._direction is Direction.LONG
        order = self._strategy.sell if long else self._strategy.buy
        stop = None
        if orders.stop is not None:
            stop = order(data=self._data, size=size, exectype=bt.Order.Stop, price=orders.stop)
            self._exit_orders.append(stop)
            self._exit_reasons[stop.ref] = orders.stop_reason
        if orders.target is not None:
            target = order(data=self._data, size=size, exectype=bt.Order.Limit, price=orders.target, oco=stop)
            self._exit_orders.append(target)
            self._exit_reasons[target.ref] = orders.target_reason
        if add is not None:
            assert self._plan is not None
            adder = self._strategy.buy if long else self._strategy.sell
            self._add_order = adder(data=self._data, size=self._plan.size, exectype=bt.Order.Stop, price=add, oco=stop)

    def _cancel_exits(self) -> None:
        """Cancels the exit orders and the add order; cancelling one of a linked group cancels them all, and a second
        cancel is a no-op."""
        for order in self._exit_orders:
            self._strategy.cancel(order)
            self._exit_reasons.pop(order.ref, None)
        self._exit_orders = []
        if self._add_order is not None:
            self._strategy.cancel(self._add_order)
            self._add_order = None

    def notify_order(self, order: bt.Order) -> None:
        is_entry = self._entry_order is not None and order.ref == self._entry_order.ref
        if is_entry and order.status in (order.Canceled, order.Margin, order.Rejected):
            self._reset()
            return
        if order.status != order.Completed:
            return
        executed = order.executed
        fill = (pd.Timestamp(bt.num2date(executed.dt)), executed.price, abs(executed.size), executed.comm)
        if is_entry:
            assert self._plan is not None
            self._fills = [fill]
            plan = self._plan
            trade = OpenTrade(self._direction, self._index(), executed.price, plan.reference, plan.stop, plan.risk)
            self._units = self._pyramid.start(trade, plan.atr) if self._pyramid.enabled else None
            self._tracker = self._rules.track(trade, (self._units,) if self._units is not None else ())
            return
        if self._add_order is not None and order.ref == self._add_order.ref:
            assert self._units is not None
            self._fills.append(fill)
            self._units.add(self._index(), executed.price)
            self._add_order = None  # the add cancelled the exit orders, which the next close submits again
            return
        reason = self._exit_reasons.get(order.ref)
        if reason is not None:
            self._record(pd.Timestamp(bt.num2date(executed.dt)), executed.price, executed.comm, reason)
            self._reset()

    def finish(self) -> None:
        """At the end of the run: a position still open is marked to the ticker's last close."""
        if self.position and self._fills:
            last_date = pd.Timestamp(self._data.datetime.datetime(0))
            self._record(last_date, self._data.close[0], 0.0, ExitReason.OPEN)

    def _record(self, exit_date: pd.Timestamp, exit_price: float, exit_commission: float, reason: str) -> None:
        assert self._plan is not None
        assert self._fills
        assert self._signal is not None
        entry_date, _, unit_size, _ = self._fills[0]
        size = sum(fill[2] for fill in self._fills)
        entry_price = sum(fill[1] * fill[2] for fill in self._fills) / size
        entry_commission = sum(fill[3] for fill in self._fills)
        direction = self._direction
        pnl = direction.sign * size * (exit_price - entry_price) - entry_commission - exit_commission
        self.trades.append(
            Trade(
                direction=direction,
                signal_date=self._signal[1],
                entry_date=entry_date,
                exit_date=exit_date,
                entry_price=entry_price,
                exit_price=exit_price,
                size=size,
                pnl=pnl,
                r_multiple=pnl / (unit_size * self._plan.risk),
                exit_reason=reason,
                adds=tuple(Fill(date, price) for date, price, _, _ in self._fills[1:]),
            )
        )


class _RulesStrategy(bt.Strategy):
    params = (("events", None), ("rules", None), ("direction", Direction.LONG), ("config", BacktestConfig()))

    def __init__(self) -> None:
        self.equity_dates: list[pd.Timestamp] = []
        self.equity_values: list[float] = []
        self._ticker = TickerOrders(self, self.data, self.p.rules, self.p.direction, Pyramiding.of(self.p.config))

    @property
    def trades(self) -> list[Trade]:
        return self._ticker.trades

    def next(self) -> None:
        self.equity_dates.append(pd.Timestamp(self.data.datetime.datetime(0)))
        self.equity_values.append(self.broker.getvalue())
        index = len(self.data) - 1
        self._ticker.update(index)
        if self._ticker.free and self.p.events[index]:
            plan = self.p.rules.plan(index, self.broker.getvalue(), self.p.config)
            if plan is not None:
                self._ticker.submit_entry(index, plan)

    def notify_order(self, order: bt.Order) -> None:
        self._ticker.notify_order(order)

    def stop(self) -> None:
        self._ticker.finish()


class CerebroEngine:
    name = "cerebro"

    def run(
        self, ticker: str, df: pd.DataFrame, signal: Signal, config: BacktestConfig, rules: TradeRules | None = None
    ) -> BacktestResult:
        prepared = (rules or TradeRules()).prepare(Bars.from_frame(df, config.atr_period), signal.direction)
        events = signal.events(df).to_numpy(dtype=bool)

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(bt.feeds.PandasData(dataname=df.loc[:, list(OHLCV_COLUMNS)], openinterest=None), name=ticker)
        cerebro.addstrategy(_RulesStrategy, events=events, rules=prepared, direction=signal.direction, config=config)
        cerebro.broker.setcash(config.initial_equity)
        cerebro.broker.setcommission(commission=config.commission_pct / 100.0, leverage=LEVERAGE)
        cerebro.broker.set_slippage_perc(config.slippage_pct / 100.0)
        strategy = cerebro.run()[0]

        equity = pd.Series(strategy.equity_values, index=pd.DatetimeIndex(strategy.equity_dates), name="equity")
        return BacktestResult(
            engine=self.name, ticker=ticker, signal=signal.name, equity=equity, trades=tuple(strategy.trades)
        )
