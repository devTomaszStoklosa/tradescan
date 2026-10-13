"""Event-driven validation with backtrader's Cerebro (optional: `pip install -e .[cerebro]`).

The signal column is precomputed by the same pandas code the scanner uses and fed to Cerebro as an
extra data line, so the rule is defined once. Cerebro adds realistic order handling: bracket orders,
percentage commission and slippage.
"""

from __future__ import annotations

import math

import pandas as pd

try:
    import backtrader as bt
except ImportError as error:  # pragma: no cover - depends on the optional extra
    raise ImportError("The cerebro engine needs backtrader: pip install -e .[cerebro]") from error

from tradescan.backtest.base import BacktestConfig, BacktestResult, ExitReason, Trade
from tradescan.data.schema import OHLCV_COLUMNS
from tradescan.indicators import atr
from tradescan.risk import position_size, trade_levels
from tradescan.signals.base import Direction, Signal


class _SignalFeed(bt.feeds.PandasData):
    lines = ("signal", "atr")
    params = (("signal", -1), ("atr", -1), ("openinterest", None))


class _SignalStrategy(bt.Strategy):
    params = (("direction", Direction.LONG), ("config", BacktestConfig()))

    def __init__(self) -> None:
        self.equity_dates: list[pd.Timestamp] = []
        self.equity_values: list[float] = []
        self.trades: list[Trade] = []
        self._reset()

    def _reset(self) -> None:
        # Notifications carry clones of orders, so orders are matched by `ref`, never by identity.
        self._entry_ref: int | None = None
        self._stop_order = None
        self._exit_reasons: dict[int, str] = {}
        self._plan: tuple[pd.Timestamp, float] | None = None  # (signal date, risk per share)
        self._entry: tuple[pd.Timestamp, float, float, float] | None = None  # (date, price, size, commission)
        self._bars_held = 0
        self._closing = False

    def next(self) -> None:
        self.equity_dates.append(pd.Timestamp(self.data.datetime.datetime(0)))
        self.equity_values.append(self.broker.getvalue())

        if self.position:
            self._bars_held += 1
            if self._bars_held >= self.p.config.max_hold_bars and not self._closing:
                self._closing = True
                self.cancel(self._stop_order)  # the bracket cancels the target with it
                self._exit_reasons[self.close().ref] = ExitReason.TIME
            return

        if self._entry_ref is not None or self.data.signal[0] <= 0 or math.isnan(self.data.atr[0]):
            return
        self._submit_entry()

    def _submit_entry(self) -> None:
        config: BacktestConfig = self.p.config
        direction: Direction = self.p.direction
        reference = self.data.close[0]
        stop, (target,), risk = trade_levels(direction, reference, self.data.atr[0], config.atr_mult, (config.target_r,))
        size = position_size(
            self.broker.getvalue(), reference, risk, config.risk_pct, config.max_position_pct, config.lot_size
        )
        if size <= 0:
            return
        bracket = self.buy_bracket if direction is Direction.LONG else self.sell_bracket
        entry, stop_order, target_order = bracket(
            size=size, exectype=bt.Order.Market, stopprice=stop, limitprice=target
        )
        self._entry_ref, self._stop_order = entry.ref, stop_order
        self._exit_reasons = {stop_order.ref: ExitReason.STOP, target_order.ref: ExitReason.TARGET}
        self._plan = (pd.Timestamp(self.data.datetime.datetime(0)), risk)

    def notify_order(self, order: bt.Order) -> None:
        is_entry = order.ref == self._entry_ref
        if is_entry and order.status in (order.Canceled, order.Margin, order.Rejected):
            self._reset()
            return
        if order.status != order.Completed:
            return
        executed = order.executed
        if is_entry:
            self._entry = (pd.Timestamp(bt.num2date(executed.dt)), executed.price, abs(executed.size), executed.comm)
            self._bars_held = 0
            return
        reason = self._exit_reasons.get(order.ref)
        if reason is not None:
            self._record(pd.Timestamp(bt.num2date(executed.dt)), executed.price, executed.comm, reason)
            self._reset()

    def stop(self) -> None:
        if self.position and self._entry is not None:
            last_date = pd.Timestamp(self.data.datetime.datetime(0))
            self._record(last_date, self.data.close[0], 0.0, ExitReason.OPEN)

    def _record(self, exit_date: pd.Timestamp, exit_price: float, exit_commission: float, reason: str) -> None:
        assert self._plan is not None and self._entry is not None
        signal_date, risk = self._plan
        entry_date, entry_price, size, entry_commission = self._entry
        direction: Direction = self.p.direction
        pnl = direction.sign * size * (exit_price - entry_price) - entry_commission - exit_commission
        self.trades.append(
            Trade(
                direction=direction,
                signal_date=signal_date,
                entry_date=entry_date,
                exit_date=exit_date,
                entry_price=entry_price,
                exit_price=exit_price,
                size=size,
                pnl=pnl,
                r_multiple=pnl / (size * risk),
                exit_reason=reason,
            )
        )


class CerebroEngine:
    name = "cerebro"

    def run(self, ticker: str, df: pd.DataFrame, signal: Signal, config: BacktestConfig) -> BacktestResult:
        feed = df.loc[:, list(OHLCV_COLUMNS)].copy()
        feed["signal"] = signal.events(df).astype(float)
        feed["atr"] = atr(df, config.atr_period)

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(_SignalFeed(dataname=feed), name=ticker)
        cerebro.addstrategy(_SignalStrategy, direction=signal.direction, config=config)
        cerebro.broker.setcash(config.initial_equity)
        cerebro.broker.setcommission(commission=config.commission_pct / 100.0)
        cerebro.broker.set_slippage_perc(config.slippage_pct / 100.0)
        strategy = cerebro.run()[0]

        equity = pd.Series(strategy.equity_values, index=pd.DatetimeIndex(strategy.equity_dates), name="equity")
        return BacktestResult(
            engine=self.name, ticker=ticker, signal=signal.name, equity=equity, trades=tuple(strategy.trades)
        )
