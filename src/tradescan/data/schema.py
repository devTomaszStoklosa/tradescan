"""The OHLCV frame shape every component of tradescan relies on."""

from __future__ import annotations

from typing import cast

import pandas as pd

OHLCV_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume")
PRICE_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close")


def normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    """Return lowercase float OHLCV columns on a sorted, tz-naive, duplicate-free DatetimeIndex.

    Rows without prices are dropped; missing volume becomes 0 (indices and some FX/crypto feeds).
    """
    renamed = frame.rename(columns=lambda column: str(column).strip().lower().replace(" ", "_"))
    missing = [column for column in OHLCV_COLUMNS if column not in renamed.columns]
    if missing:
        raise ValueError(f"OHLCV frame is missing columns: {', '.join(missing)}")

    result = renamed.loc[:, list(OHLCV_COLUMNS)].astype(float)
    index = pd.DatetimeIndex(result.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    result.index = index.rename("date")
    result = result[~result.index.duplicated(keep="last")].sort_index()
    result = result.dropna(subset=list(PRICE_COLUMNS))
    result["volume"] = result["volume"].fillna(0.0)
    return result


def bar_dates(data: pd.DataFrame | pd.Series) -> pd.DatetimeIndex:
    """The dates of normalized bars, or of a series aligned with them, as the DatetimeIndex they are."""
    return cast(pd.DatetimeIndex, data.index)


def bar_position(dates: pd.Index, date: pd.Timestamp) -> int:
    """The position of `date` among unique bar dates; a KeyError when it is not one of them."""
    return cast(int, dates.get_loc(date))
