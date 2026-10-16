"""Vectorized technical indicators.

Every function is causal: the value at bar t uses only data up to and including bar t,
so signals built on top of them never look into the future.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rma(series: pd.Series, period: int) -> pd.Series:
    """Wilder's moving average (used by RSI, ATR, ADX), seeded with the simple mean of the first `period` values."""
    values = series.astype(float)
    valid = values.notna().to_numpy()
    if valid.sum() < period:
        return pd.Series(np.nan, index=series.index, dtype=float)
    start = int(np.argmax(valid))
    seed_position = start + period - 1
    seeded = values.copy()
    seeded.iloc[seed_position] = values.iloc[start : seed_position + 1].mean()
    seeded.iloc[:seed_position] = np.nan
    return seeded.ewm(alpha=1.0 / period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = rma(delta.clip(lower=0.0), period)
    loss = rma(-delta.clip(upper=0.0), period)
    total = gain + loss
    values = 100.0 * gain / total.replace(0.0, np.nan)
    # A perfectly flat window has no gains or losses: treat it as neutral.
    return values.mask((total == 0.0) & gain.notna(), 50.0)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    signal_line = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": signal_line, "hist": line - signal_line})


def true_range(df: pd.DataFrame) -> pd.Series:
    previous_close = df["close"].shift(1)
    ranges = pd.concat(
        [df["high"] - df["low"], (df["high"] - previous_close).abs(), (df["low"] - previous_close).abs()],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return rma(true_range(df), period)


def bollinger(close: pd.Series, period: int = 20, mult: float = 2.0) -> pd.DataFrame:
    mid = sma(close, period)
    width = close.rolling(period, min_periods=period).std(ddof=0) * mult
    return pd.DataFrame({"mid": mid, "upper": mid + width, "lower": mid - width})


def percent_b(close: pd.Series, period: int = 20, mult: float = 2.0) -> pd.Series:
    """Where the close sits in its Bollinger Bands: 0 at the lower band, 1 at the upper, NaN without width."""
    bands = bollinger(close, period, mult)
    return (close - bands["lower"]) / (bands["upper"] - bands["lower"]).replace(0.0, np.nan)


def internal_bar_strength(df: pd.DataFrame) -> pd.Series:
    """Where the close sits in the bar's range: 0 at the low, 1 at the high, NaN for a bar without range."""
    return (df["close"] - df["low"]) / (df["high"] - df["low"]).replace(0.0, np.nan)


def keltner(df: pd.DataFrame, period: int = 20, mult: float = 1.5) -> pd.DataFrame:
    mid = ema(df["close"], period)
    band = atr(df, period) * mult
    return pd.DataFrame({"mid": mid, "upper": mid + band, "lower": mid - band})


def donchian(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "upper": df["high"].rolling(period, min_periods=period).max(),
            "lower": df["low"].rolling(period, min_periods=period).min(),
        }
    )


def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0).where(up_move.notna())
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0).where(down_move.notna())
    smoothed_range = rma(true_range(df).where(up_move.notna()), period).replace(0.0, np.nan)
    plus_di = 100.0 * rma(plus_dm, period) / smoothed_range
    minus_di = 100.0 * rma(minus_dm, period) / smoothed_range
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return pd.DataFrame({"plus_di": plus_di, "minus_di": minus_di, "adx": rma(dx, period)})


def supertrend(df: pd.DataFrame, period: int = 10, mult: float = 3.0) -> pd.DataFrame:
    """Supertrend line and direction (+1 up, -1 down).

    The trailing bands depend on their own previous values, so this one indicator uses a numpy loop.
    """
    atr_values = atr(df, period).to_numpy()
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    mid = (high + low) / 2.0
    basic_upper = mid + mult * atr_values
    basic_lower = mid - mult * atr_values

    size = len(df)
    upper = np.full(size, np.nan)
    lower = np.full(size, np.nan)
    direction = np.full(size, np.nan)
    line = np.full(size, np.nan)
    for i in range(size):
        if np.isnan(atr_values[i]):
            continue
        if i == 0 or np.isnan(direction[i - 1]):
            upper[i], lower[i], direction[i] = basic_upper[i], basic_lower[i], 1.0
        else:
            upper[i] = basic_upper[i] if basic_upper[i] < upper[i - 1] or close[i - 1] > upper[i - 1] else upper[i - 1]
            lower[i] = basic_lower[i] if basic_lower[i] > lower[i - 1] or close[i - 1] < lower[i - 1] else lower[i - 1]
            if direction[i - 1] < 0 and close[i] > upper[i]:
                direction[i] = 1.0
            elif direction[i - 1] > 0 and close[i] < lower[i]:
                direction[i] = -1.0
            else:
                direction[i] = direction[i - 1]
        line[i] = lower[i] if direction[i] > 0 else upper[i]
    return pd.DataFrame({"line": line, "direction": direction}, index=df.index)


def relative_volume(volume: pd.Series, period: int = 20) -> pd.Series:
    """Today's volume divided by the average of the previous `period` bars."""
    baseline = volume.rolling(period, min_periods=period).mean().shift(1)
    return volume / baseline.replace(0.0, np.nan)


def rate_of_change(close: pd.Series, period: int) -> pd.Series:
    return close / close.shift(period) - 1.0
