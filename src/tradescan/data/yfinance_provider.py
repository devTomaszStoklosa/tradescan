"""DataProvider backed by Yahoo Finance through the yfinance package."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any, cast

import pandas as pd

from tradescan.data.schema import normalize_ohlcv

logger = logging.getLogger(__name__)

Downloader = Callable[..., pd.DataFrame]


def _yfinance_download(*args: Any, **kwargs: Any) -> pd.DataFrame:
    import yfinance as yf

    frame: pd.DataFrame = yf.download(*args, **kwargs)
    return frame


class YFinanceProvider:
    """Downloads all tickers in one batched request (prices adjusted for splits and dividends)."""

    def __init__(self, downloader: Downloader | None = None) -> None:
        self._download = downloader or _yfinance_download

    def history(self, tickers: Sequence[str], period: str, interval: str) -> dict[str, pd.DataFrame]:
        if not tickers:
            return {}
        raw = self._download(
            list(tickers),
            period=period,
            interval=interval,
            auto_adjust=True,
            group_by="ticker",
            threads=True,
            progress=False,
        )
        return split_download(raw, tickers)


def split_download(raw: pd.DataFrame | None, tickers: Sequence[str]) -> dict[str, pd.DataFrame]:
    """Split a yfinance download (MultiIndex or flat columns) into one normalized frame per ticker."""
    if raw is None or raw.empty:
        return {}
    if not isinstance(raw.columns, pd.MultiIndex):
        return _single(raw, tickers[0]) if len(tickers) == 1 else {}

    level = _ticker_level(raw.columns, tickers)
    available = set(raw.columns.get_level_values(level))
    frames: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        if ticker in available:
            frames.update(_single(cast(pd.DataFrame, raw.xs(ticker, axis=1, level=level)), ticker))
    return frames


def _ticker_level(columns: pd.MultiIndex, tickers: Sequence[str]) -> int:
    first_level = set(columns.get_level_values(0))
    return 0 if any(ticker in first_level for ticker in tickers) else 1


def _single(frame: pd.DataFrame, ticker: str) -> dict[str, pd.DataFrame]:
    frame = frame.dropna(how="all")
    if frame.empty:
        logger.warning("No data returned for %s", ticker)
        return {}
    try:
        return {ticker: normalize_ohlcv(frame)}
    except ValueError as error:
        logger.warning("Skipping %s: %s", ticker, error)
        return {}
