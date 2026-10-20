"""Report helpers the commands share: missing tickers, exports, progress notes and captions."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from tradescan.backtest.base import BacktestConfig
from tradescan.report.console import ConsoleReport
from tradescan.report.export import export_frame


def pyramiding(config: BacktestConfig) -> str:
    """The pyramiding of a backtest for its caption; empty without it."""
    if config.max_units <= 1:
        return ""
    return f", pyramiding up to {config.max_units} units {config.add_every_atr:g} ATR apart"


def missing(report: ConsoleReport, missing: Sequence[str]) -> None:
    if missing:
        report.warning(f"No data for: {', '.join(missing)}")


def export(report: ConsoleReport, frame: pd.DataFrame, target: str | None) -> None:
    if target:
        report.note(f"Saved {export_frame(frame, Path(target))}")


def loading(report: ConsoleReport, count: int, period: str) -> None:
    report.note(f"Loading {count} tickers ({period})...")
