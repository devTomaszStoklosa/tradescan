"""Abstraction over market data sources."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import pandas as pd


class DataProvider(Protocol):
    def history(self, tickers: Sequence[str], period: str, interval: str) -> dict[str, pd.DataFrame]:
        """Return normalized OHLCV frames (see `schema.normalize_ohlcv`) keyed by ticker.

        Tickers without data are omitted from the result instead of raising.
        """
        ...
