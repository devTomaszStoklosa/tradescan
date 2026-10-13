"""Turn domain results into DataFrames shared by the terminal view and file export."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, fields

import pandas as pd

from tradescan.backtest.base import BacktestResult, Trade
from tradescan.backtest.edge import EdgeStats
from tradescan.backtest.metrics import Metrics
from tradescan.scanner import ScanHit
from tradescan.scoring import Scorer
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
                "description": signal.description,
            }
            for signal in signals
        ]
    )


def edge_to_frame(rows: Sequence[tuple[Signal, Sequence[EdgeStats]]]) -> pd.DataFrame:
    records = []
    for signal, stats in rows:
        record: dict[str, object] = {"signal": signal.name, "dir": signal.direction.value, "family": signal.family.value}
        for item in stats:
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


def metrics_to_frame(results: Sequence[tuple[BacktestResult, Metrics]]) -> pd.DataFrame:
    return pd.DataFrame(
        {result.engine: {item.name: getattr(metrics, item.name) for item in fields(metrics)} for result, metrics in results}
    )


def trades_to_frame(trades: Sequence[Trade], engine: str = "") -> pd.DataFrame:
    frame = pd.DataFrame([asdict(trade) for trade in trades])
    if frame.empty:
        return frame
    frame["direction"] = frame["direction"].astype(str)
    for column in ("signal_date", "entry_date", "exit_date"):
        frame[column] = pd.to_datetime(frame[column]).dt.date.astype(str)
    if engine:
        frame.insert(0, "engine", engine)
    return frame
