"""Parquet cache that decorates any DataProvider."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import pandas as pd

from tradescan.data.provider import DataProvider

logger = logging.getLogger(__name__)


class CachedProvider:
    """Serves fresh cached frames from disk and fetches only stale or missing tickers, in one batch."""

    def __init__(
        self,
        inner: DataProvider,
        directory: Path,
        ttl_seconds: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._inner = inner
        self._directory = directory
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    def history(self, tickers: Sequence[str], period: str, interval: str) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        stale: list[str] = []
        for ticker in tickers:
            cached = self._read(self._path(ticker, period, interval))
            if cached is None:
                stale.append(ticker)
            else:
                frames[ticker] = cached

        if stale:
            for ticker, frame in self._inner.history(stale, period, interval).items():
                self._write(self._path(ticker, period, interval), frame)
                frames[ticker] = frame

        return {ticker: frames[ticker] for ticker in tickers if ticker in frames}

    def _path(self, ticker: str, period: str, interval: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", ticker)
        return self._directory / interval / period / f"{safe}.parquet"

    def _read(self, path: Path) -> pd.DataFrame | None:
        if not path.is_file() or self._clock() - path.stat().st_mtime > self._ttl_seconds:
            return None
        try:
            return pd.read_parquet(path)
        except (OSError, ValueError) as error:
            logger.warning("Ignoring unreadable cache file %s: %s", path, error)
            return None

    def _write(self, path: Path, frame: pd.DataFrame) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        frame.to_parquet(temporary)
        temporary.replace(path)
