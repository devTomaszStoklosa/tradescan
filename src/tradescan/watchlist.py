"""Watchlist files: tickers separated by whitespace or commas, `#` comments.

A comment line `# benchmark: SPY` sets the benchmark used for relative strength and market regime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_BENCHMARK_DIRECTIVE = re.compile(r"^#\s*benchmark\s*:\s*(\S+)", re.IGNORECASE)


@dataclass(frozen=True)
class Watchlist:
    name: str
    tickers: tuple[str, ...]
    benchmark: str | None = None


def parse_watchlist(name: str, text: str) -> Watchlist:
    tickers: list[str] = []
    benchmark: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        directive = _BENCHMARK_DIRECTIVE.match(line)
        if directive:
            benchmark = directive.group(1).upper()
            continue
        content = line.split("#", 1)[0]
        for token in re.split(r"[\s,;]+", content):
            if token and token.upper() not in tickers:
                tickers.append(token.upper())
    return Watchlist(name=name, tickers=tuple(tickers), benchmark=benchmark)


def from_tickers(tickers: str) -> Watchlist:
    """Build an ad-hoc watchlist from a comma separated string."""
    return parse_watchlist("custom", tickers)


def available_watchlists(directory: Path) -> list[str]:
    return sorted(path.stem for path in directory.glob("*.txt"))


def load_watchlist(reference: str, directory: Path) -> Watchlist:
    """Load a watchlist by file path or by name from `directory` (`wig20` -> `wig20.txt`)."""
    candidate = Path(reference)
    if not candidate.is_file():
        candidate = directory / f"{reference}.txt"
    if not candidate.is_file():
        names = ", ".join(available_watchlists(directory)) or "none"
        raise FileNotFoundError(f"Watchlist '{reference}' not found. Available in {directory}: {names}")
    return parse_watchlist(candidate.stem, candidate.read_text(encoding="utf-8"))
