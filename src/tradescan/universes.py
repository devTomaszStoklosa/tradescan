"""Index universes (S&P 500, Nasdaq-100) refreshed from the constituent tables on Wikipedia."""

from __future__ import annotations

import io
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from tradescan.watchlist import parse_watchlist

Fetcher = Callable[[str], str]

_USER_AGENT = "tradescan/0.1 (personal research tool)"


@dataclass(frozen=True)
class UniverseSource:
    name: str  # watchlist file name, e.g. sp500 -> sp500.txt
    title: str
    url: str
    column: str  # table column holding the symbols
    benchmark: str
    min_members: int  # sanity floor: fewer rows means the page layout changed


SOURCES: tuple[UniverseSource, ...] = (
    UniverseSource(
        name="sp500",
        title="S&P 500",
        url="https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        column="Symbol",
        benchmark="SPY",
        min_members=480,
    ),
    UniverseSource(
        name="nasdaq100",
        title="Nasdaq-100",
        url="https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies",
        column="Ticker",
        benchmark="QQQ",
        min_members=95,
    ),
)


@dataclass(frozen=True)
class UpdateResult:
    source: UniverseSource
    path: Path
    tickers: tuple[str, ...]
    created: bool
    added: tuple[str, ...]
    removed: tuple[str, ...]


def http_fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        body: bytes = response.read()
        return body.decode("utf-8")


def yahoo_symbol(symbol: str) -> str:
    """Yahoo writes share classes with a dash: BRK.B -> BRK-B."""
    return symbol.strip().upper().replace(".", "-")


def parse_constituents(html: str, source: UniverseSource) -> tuple[str, ...]:
    """Symbols from the first table on the page that has the source's symbol column."""
    for table in pd.read_html(io.StringIO(html)):
        if source.column in table.columns:
            symbols = [yahoo_symbol(str(value)) for value in table[source.column].dropna()]
            tickers = tuple(dict.fromkeys(symbol for symbol in symbols if symbol))
            break
    else:
        raise ValueError(f"{source.title}: no table with a '{source.column}' column at {source.url}")
    if len(tickers) < source.min_members:
        raise ValueError(
            f"{source.title}: only {len(tickers)} members found (expected at least {source.min_members}); "
            "the page layout may have changed"
        )
    return tickers


def render_watchlist(source: UniverseSource, tickers: Sequence[str], as_of: date) -> str:
    lines = [
        f"# {source.title} constituents ({len(tickers)}), from {source.url} on {as_of.isoformat()}",
        "# Refresh with: tradescan update-universes",
        f"# benchmark: {source.benchmark}",
    ]
    lines += [" ".join(tickers[start : start + 10]) for start in range(0, len(tickers), 10)]
    return "\n".join(lines) + "\n"


def update_universe(
    source: UniverseSource,
    directory: Path,
    fetch: Fetcher = http_fetch,
    today: Callable[[], date] = date.today,
) -> UpdateResult:
    """Download, validate and write `<name>.txt`. On any error the existing file is left untouched."""
    tickers = parse_constituents(fetch(source.url), source)
    path = directory / f"{source.name}.txt"
    created = not path.is_file()
    previous = set() if created else set(parse_watchlist(source.name, path.read_text(encoding="utf-8")).tickers)

    directory.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(render_watchlist(source, tickers, today()), encoding="utf-8")
    temporary.replace(path)
    return UpdateResult(
        source=source,
        path=path,
        tickers=tickers,
        created=created,
        added=() if created else tuple(sorted(set(tickers) - previous)),
        removed=tuple(sorted(previous - set(tickers))),
    )
