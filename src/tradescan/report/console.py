"""Terminal rendering with rich."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from tradescan.regime import MarketRegime, Regime

_SIGNED_COLUMNS = ("chg%", "edge avg%", "edge vs base%", "avg%", "vs base%")
_REGIME_STYLE = {Regime.RISK_ON: "bold green", Regime.NEUTRAL: "bold yellow", Regime.RISK_OFF: "bold red"}


class ConsoleReport:
    def __init__(self, console: Console) -> None:
        self._console = console

    def frame(
        self,
        frame: pd.DataFrame,
        title: str,
        columns: Sequence[str] | None = None,
        caption: str | None = None,
        show_index: bool = False,
    ) -> None:
        if frame.empty:
            self._console.print(f"[dim]{escape(title)}: nothing to show.[/]")
            return
        view = frame.loc[:, [column for column in columns if column in frame.columns]] if columns else frame
        table = Table(title=title, caption=caption, header_style="bold cyan", show_lines=False)
        if show_index:
            table.add_column("", style="bold")
        for column in view.columns:
            numeric = pd.api.types.is_numeric_dtype(view[column])
            table.add_column(str(column), justify="right" if numeric else "left", overflow="fold")
        for label, row in view.iterrows():
            cells = [_cell(str(column), value) for column, value in row.items()]
            table.add_row(*([escape(str(label))] if show_index else []), *cells)
        self._console.print(table)

    def regime(self, regime: MarketRegime) -> None:
        benchmark_state = {True: "[green]above[/]", False: "[red]below[/]", None: "[dim]n/a[/]"}
        lines = [
            f"Regime: [{_REGIME_STYLE[regime.regime]}]{regime.regime.value.upper()}[/]",
            f"{escape(regime.benchmark)} {_number(regime.benchmark_close)} is "
            f"{benchmark_state[regime.benchmark_above_slow]} SMA200, "
            f"SMA50 {benchmark_state[regime.benchmark_fast_above_slow]} SMA200",
            f"Breadth: {_number(regime.pct_above_fast, 0)}% above SMA50, "
            f"{_number(regime.pct_above_slow, 0)}% above SMA200 (of {regime.universe_size})",
            f"52-week highs / lows today: [green]{regime.new_highs}[/] / [red]{regime.new_lows}[/]",
        ]
        self._console.print("\n".join(lines))

    def note(self, message: str) -> None:
        self._console.print(f"[dim]{escape(message)}[/]")

    def warning(self, message: str) -> None:
        self._console.print(f"[yellow]{escape(message)}[/]")


def _cell(column: str, value: object) -> str:
    if column == "dir":
        return "[green]long[/]" if value == "long" else "[red]short[/]"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = _number(value)
        if column in _SIGNED_COLUMNS and not math.isnan(value):
            return f"[green]{text}[/]" if value > 0 else f"[red]{text}[/]" if value < 0 else text
        return text
    return escape(str(value))


def _number(value: float, decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    if math.isinf(value):
        return "inf"
    return f"{value:,.{decimals}f}"
