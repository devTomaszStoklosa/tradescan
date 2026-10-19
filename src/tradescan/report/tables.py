"""Turn domain results into DataFrames shared by the terminal view and file export."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, fields

import pandas as pd

from tradescan.backtest.base import Trade
from tradescan.backtest.oos import PeriodMetrics
from tradescan.backtest.portfolio import PortfolioTrade
from tradescan.backtest.portfolio_metrics import TickerContribution
from tradescan.backtest.rotation import Targets
from tradescan.backtest.tickers import Period
from tradescan.scanner import ScanHit
from tradescan.scoring import Scorer
from tradescan.services import (
    METRIC_NAMES,
    EdgeRow,
    EngineRun,
    PortfolioReport,
    RotationReport,
    SweepReport,
    WalkForwardReport,
    WatchlistBacktestReport,
    WindowPick,
)
from tradescan.signals.base import Signal

SCAN_COLUMNS: tuple[str, ...] = (
    "ticker", "dir", "score", "signals", "close", "chg%", "trend D/W", "RS%", "ATR%",
    "stop", "target 1", "size", "risk $", "edge N", "edge win%", "edge avg%", "edge vs base%",
)  # fmt: skip


def hits_to_frame(hits: Sequence[ScanHit]) -> pd.DataFrame:
    return pd.DataFrame([_hit_row(hit) for hit in hits], columns=None if hits else list(SCAN_COLUMNS))


def _hit_row(hit: ScanHit) -> dict[str, object]:
    context, risk, edge = hit.context, hit.risk, hit.edge
    row: dict[str, object] = {
        "ticker": hit.ticker,
        "dir": hit.direction.value,
        "score": hit.score.total,
        "signals": ", ".join(f"{item.signal.name}({item.bars_ago})" for item in hit.fired),
        "close": context.close,
        "chg%": context.change_pct,
        "trend D/W": f"{context.daily_trend.value}/{context.weekly_trend.value}",
        "RS%": hit.rs_percentile,
        "ATR%": context.atr_pct,
        "stop": risk.stop,
    }
    row.update({f"target {number}": price for number, price in enumerate(risk.targets, start=1)})
    row.update(
        {
            "size": risk.size,
            "risk $": risk.risk_amount,
            "edge N": edge.events if edge else 0,
            "edge win%": edge.win_rate if edge else math.nan,
            "edge avg%": edge.mean_return if edge else math.nan,
            "edge vs base%": edge.edge if edge else math.nan,
            "edge horizon": edge.horizon if edge else math.nan,
            "date": context.date.date().isoformat(),
            "adx": context.adx,
            "score signals": hit.score.signals,
            "score trend": hit.score.trend,
            "score weekly": hit.score.weekly,
            "score rs": hit.score.relative_strength,
        }
    )
    return row


def signals_to_frame(signals: Sequence[Signal], scorer: Scorer) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "name": signal.name,
                "family": signal.family.value,
                "dir": signal.direction.value,
                "weight": scorer.weight(signal),
                "description": signal.describe(),
            }
            for signal in signals
        ]
    )


def edge_to_frame(rows: Sequence[EdgeRow]) -> pd.DataFrame:
    records = []
    for row in rows:
        signal = row.signal
        record: dict[str, object] = {
            "signal": signal.name,
            "dir": signal.direction.value,
            "family": signal.family.value,
        }
        for item in row.stats:
            suffix = f" {item.horizon}d"
            record.update(
                {
                    f"N{suffix}": item.events,
                    f"win%{suffix}": item.win_rate,
                    f"avg%{suffix}": item.mean_return,
                    f"vs base%{suffix}": item.edge,
                }
            )
        records.append(record)
    return pd.DataFrame(records)


def metrics_to_frame(runs: Sequence[EngineRun]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            run.result.engine: {item.name: getattr(run.metrics, item.name) for item in fields(run.metrics)}
            for run in runs
        }
    )


FEW_TRADES = 20  # fewer closed trades than this are too few to trust


def periods_to_frame(runs: Sequence[EngineRun]) -> pd.DataFrame:
    """In-sample and out-of-sample metrics of every engine that has them."""
    columns = {}
    for run in runs:
        if run.periods is None:
            continue
        for label, metrics in (("in-sample", run.periods.in_sample), ("out-of-sample", run.periods.out_of_sample)):
            columns[f"{run.result.engine} {label}"] = {
                item.name: getattr(metrics, item.name) for item in fields(metrics)
            }
    return pd.DataFrame(columns)


def sweep_to_frame(report: SweepReport, metric: str, out_of_sample: bool) -> pd.DataFrame:
    """One period's `metric` per combination: columns are the first axis's values, rows the second's.

    A value from fewer than FEW_TRADES trades is marked with *, a combination that could not run shows "error".
    """
    first = report.parameters[0].axis
    second = report.parameters[1].axis if len(report.parameters) > 1 else None
    rows: dict[str, dict[str, str]] = {}
    for cell in report.cells:
        row = f"{second.name}={cell.values[1]:g}" if second else metric
        rows.setdefault(row, {})[f"{first.name}={cell.values[0]:g}"] = _sweep_cell(cell.periods, metric, out_of_sample)
    return pd.DataFrame.from_dict(rows, orient="index")


def _sweep_cell(periods: PeriodMetrics | None, metric: str, out_of_sample: bool) -> str:
    if periods is None:
        return "error"
    metrics = periods.out_of_sample if out_of_sample else periods.in_sample
    value = getattr(metrics, metric)
    text = "-" if math.isnan(value) else "inf" if math.isinf(value) else f"{value:,.2f}"
    return f"{text}*" if metrics.trades < FEW_TRADES else text


def sweep_cells_frame(report: SweepReport) -> pd.DataFrame:
    """Every combination with both periods' metrics, one row each (for export)."""
    records = []
    for cell in report.cells:
        record: dict[str, object] = {item.axis.key: value for item, value in zip(report.parameters, cell.values)}
        record["error"] = cell.error or ""
        if cell.periods is not None:
            for prefix, metrics in (("is", cell.periods.in_sample), ("oos", cell.periods.out_of_sample)):
                record.update({f"{prefix}_{item.name}": getattr(metrics, item.name) for item in fields(metrics)})
        records.append(record)
    return pd.DataFrame(records)


def _picked(report: WalkForwardReport, pick: WindowPick) -> str:
    """The values a window picked, e.g. "oversold=10, target_r=2"."""
    if pick.combination is None:
        return "none qualified"
    values = report.combinations[pick.combination].values
    return ", ".join(f"{item.axis.name}={value:g}" for item, value in zip(report.parameters, values))


def _dates(index: pd.DatetimeIndex, first: int, last: int) -> str:
    return f"{index[first].date()} to {index[last].date()}"


def walk_forward_windows_frame(report: WalkForwardReport) -> pd.DataFrame:
    """One row per window: its in-sample and out-of-sample dates, the bars its pick traded, the pick and its
    in-sample metric, and the out-of-sample metric, trades and return of the bars it traded."""
    index, metric = report.close.index, report.metric
    records = []
    for number, item in enumerate(report.windows, start=1):
        window, pick, segment, out = item.window, item.pick, item.segment, item.out_of_sample
        records.append(
            {
                "window": number,
                "in-sample": _dates(index, window.in_sample.start, window.in_sample.end - 1),
                "out-of-sample": _dates(index, window.out_of_sample.start, window.out_of_sample.end - 1),
                "traded": _dates(index, segment.start, segment.end) if segment.traded else "-",
                "pick": _picked(report, pick),
                "qualified": pick.qualified,
                f"IS {metric}": getattr(pick.in_sample, metric) if pick.in_sample else math.nan,
                f"OOS {metric}": getattr(out, metric) if out else math.nan,
                "OOS trades": out.trades if out else 0,
                "OOS return%": out.total_return_pct if out else math.nan,
            }
        )
    return pd.DataFrame(records)


def walk_forward_metrics_frame(report: WalkForwardReport) -> pd.DataFrame:
    """The stitched out-of-sample curve's metrics next to the unchanged setup's on the same bars."""
    columns = {"walk-forward": report.metrics, "unchanged setup": report.unchanged_metrics}
    return pd.DataFrame(
        {
            label: {item.name: getattr(metrics, item.name) for item in fields(metrics)}
            for label, metrics in columns.items()
        }
    )


def walk_forward_pick(report: WalkForwardReport, pick: WindowPick) -> str:
    """A window's pick with the dates of the in-sample window that picked it."""
    return f"{_picked(report, pick)} (in-sample {_dates(report.close.index, pick.span.start, pick.span.end - 1)})"


def walk_forward_export_frame(report: WalkForwardReport) -> pd.DataFrame:
    """One row per window with its dates, the picked values and every metric of both periods (for export)."""
    index = report.close.index
    no_pick = (math.nan,) * len(report.parameters)
    records = []
    for number, item in enumerate(report.windows, start=1):
        window, pick, segment = item.window, item.pick, item.segment
        record: dict[str, object] = {
            "window": number,
            "is_start": index[window.in_sample.start].date().isoformat(),
            "is_end": index[window.in_sample.end - 1].date().isoformat(),
            "oos_start": index[window.out_of_sample.start].date().isoformat(),
            "oos_end": index[window.out_of_sample.end - 1].date().isoformat(),
            "traded_from": index[segment.start].date().isoformat() if segment.traded else "",
            "traded_to": index[segment.end].date().isoformat() if segment.traded else "",
            "qualified": pick.qualified,
        }
        values = report.combinations[pick.combination].values if pick.combination is not None else no_pick
        record.update({parameter.axis.key: value for parameter, value in zip(report.parameters, values)})
        for prefix, metrics in (("is", pick.in_sample), ("oos", item.out_of_sample)):
            if metrics is not None:
                record.update({f"{prefix}_{field.name}": getattr(metrics, field.name) for field in fields(metrics)})
        records.append(record)
    return pd.DataFrame(records)


PERIOD_LABELS = {Period.FULL: "full", Period.IN_SAMPLE: "in-sample", Period.OUT_OF_SAMPLE: "out-of-sample"}


def watchlist_rows_frame(report: WatchlistBacktestReport, metric: str) -> pd.DataFrame:
    """One row per ticker: trades and `metric` in every period, then the full history's return, drawdown and
    buy & hold; the best full-history `metric` first, tickers without a value last."""
    records = []
    for row in report.rows:
        record: dict[str, object] = {"ticker": row.ticker}
        parts = {period: row.run.period(period) for period in Period}
        for period, part in parts.items():
            record[f"trades {PERIOD_LABELS[period]}"] = str(part.metrics.trades) if part else "-"  # no split: no count
        for period, part in parts.items():
            record[f"{metric} {PERIOD_LABELS[period]}"] = getattr(part.metrics, metric) if part else math.nan
        full = row.run.full.metrics
        record.update(
            {"return%": full.total_return_pct, "max DD%": full.max_drawdown_pct, "buy&hold%": full.buy_hold_pct}
        )
        records.append(record)
    frame = pd.DataFrame(records)
    return frame.sort_values(f"{metric} full", ascending=False, na_position="last", kind="stable", ignore_index=True)


def spread_frame(report: WatchlistBacktestReport, metric: str) -> pd.DataFrame:
    """How `metric` is spread across the tickers, one row per period."""
    rows = {}
    for period, summary in report.periods.items():
        spread = summary.spreads[metric]
        rows[PERIOD_LABELS[period]] = {
            "tickers": spread.tickers,
            "median": spread.median,
            "25%": spread.p25,
            "75%": spread.p75,
            "min": spread.minimum,
            "max": spread.maximum,
            "above break-even%": spread.above_break_even_pct,
        }
    return _whole_counts(pd.DataFrame.from_dict(rows, orient="index"), "tickers")


def pooled_frame(report: WatchlistBacktestReport) -> pd.DataFrame:
    """Every ticker's closed trades taken together, one row per period."""
    rows = {}
    for period, summary in report.periods.items():
        pooled = summary.pooled
        rows[PERIOD_LABELS[period]] = {
            "tickers": summary.tickers,
            "trades": pooled.trades,
            "win%": pooled.win_rate_pct,
            "expectancy R": pooled.expectancy_r,
            "profit factor R": pooled.profit_factor_r,
            "SQN": pooled.sqn,
        }
    return _whole_counts(pd.DataFrame.from_dict(rows, orient="index"), "tickers", "trades")


def _whole_counts(frame: pd.DataFrame, *columns: str) -> pd.DataFrame:
    """Counts kept as Python ints, so a row that also holds floats still shows them as whole numbers."""
    return frame.astype({column: object for column in columns})


def watchlist_export_frame(report: WatchlistBacktestReport) -> pd.DataFrame:
    """Every ticker with every metric of every period, one row each (for export)."""
    prefixes = {Period.FULL: "full", Period.IN_SAMPLE: "is", Period.OUT_OF_SAMPLE: "oos"}
    records = []
    for row in report.rows:
        split = row.run.split
        record: dict[str, object] = {
            "ticker": row.ticker,
            "start": row.start.date().isoformat(),
            "end": row.end.date().isoformat(),
            "oos_start": split.out_of_sample[0].date().isoformat() if split else "",
        }
        for period, prefix in prefixes.items():
            part = row.run.period(period)
            record.update(
                {f"{prefix}_{name}": getattr(part.metrics, name) if part else math.nan for name in METRIC_NAMES}
            )
        records.append(record)
    return pd.DataFrame(records)


def trades_to_frame(trades: Sequence[Trade], engine: str = "") -> pd.DataFrame:
    frame = pd.DataFrame([asdict(trade) for trade in trades])
    if frame.empty:
        return frame
    frame["direction"] = frame["direction"].astype(str)
    for column in ("signal_date", "entry_date", "exit_date"):
        frame[column] = pd.to_datetime(frame[column]).dt.date.astype(str)
    frame["units"] = [trade.units for trade in trades]
    frame["adds"] = [
        "; ".join(f"{fill.date.date().isoformat()} {fill.price:g}" for fill in trade.adds) for trade in trades
    ]
    if engine:
        frame.insert(0, "engine", engine)
    return frame


def portfolio_metrics_frame(report: PortfolioReport) -> pd.DataFrame:
    """Every engine's metrics and portfolio stats of the full history and of each period, one column each."""
    columns = {}
    for run in report.runs:
        for label, period in (("full", run.full), ("in-sample", run.in_sample), ("out-of-sample", run.out_of_sample)):
            if period is None:
                continue
            values = {item.name: getattr(period.metrics, item.name) for item in fields(period.metrics)}
            values.update({item.name: getattr(period.stats, item.name) for item in fields(period.stats)})
            columns[f"{run.result.engine} {label}"] = values
    return pd.DataFrame(columns)


def rotation_metrics_frame(report: RotationReport) -> pd.DataFrame:
    """The metrics and rotation stats of the full run and of each period, one column each."""
    columns = {}
    for label, period in (
        ("full", report.full),
        ("in-sample", report.in_sample),
        ("out-of-sample", report.out_of_sample),
    ):
        if period is None:
            continue
        values = {item.name: getattr(period.metrics, item.name) for item in fields(period.metrics)}
        values.update({item.name: getattr(period.stats, item.name) for item in fields(period.stats)})
        columns[label] = values
    return pd.DataFrame(columns)


def targets_frame(targets: Targets) -> pd.DataFrame:
    """A rebalance's picks by rank; a pick that is not held handed its slot to the safe asset or cash."""
    return pd.DataFrame(
        [
            {
                "ticker": pick.ticker,
                "score": pick.score,
                "momentum%": pick.momentum * 100.0,
                "weight%": pick.weight_pct,
                "held": "yes" if pick.held else "no",
            }
            for pick in targets.picks
        ]
    )


def contributions_frame(rows: Sequence[TickerContribution]) -> pd.DataFrame:
    """Every ticker's share of the portfolio's result, the largest P&L first."""
    frame = pd.DataFrame([asdict(row) for row in rows])
    return frame if frame.empty else frame.sort_values("pnl", ascending=False, kind="stable").reset_index(drop=True)


def portfolio_trades_frame(trades: Sequence[PortfolioTrade], engine: str = "") -> pd.DataFrame:
    frame = trades_to_frame([item.trade for item in trades], engine)
    if not frame.empty:
        frame.insert(1 if engine else 0, "ticker", [item.ticker for item in trades])
    return frame
