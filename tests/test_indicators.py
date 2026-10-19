import numpy as np
import pandas as pd
import pytest
from tests.synthetic import make_ohlcv, random_walk

from tradescan import indicators as ind


def test_sma_and_ema_basics():
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert ind.sma(series, 3).tolist()[2:] == [2.0, 3.0, 4.0]
    assert ind.sma(series, 3).isna().sum() == 2
    assert ind.ema(pd.Series([7.0] * 30), 10).dropna().eq(7.0).all()


def test_rma_is_seeded_with_simple_mean_then_wilder_smoothed():
    values = ind.rma(pd.Series(np.arange(1.0, 11.0)), 3)
    assert values.iloc[:2].isna().all()
    assert values.iloc[2] == pytest.approx(2.0)
    assert values.iloc[3] == pytest.approx((2.0 * 2 + 4.0) / 3)


def test_rsi_matches_wilder_recursion():
    close = random_walk(300)["close"]
    period = 14
    delta = close.diff().to_numpy()
    gains, losses = np.clip(delta, 0, None), np.clip(-delta, 0, None)
    avg_gain, avg_loss = gains[1 : period + 1].mean(), losses[1 : period + 1].mean()
    expected = [100 * avg_gain / (avg_gain + avg_loss)]
    for i in range(period + 1, len(close)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        expected.append(100 * avg_gain / (avg_gain + avg_loss))
    actual = ind.rsi(close, period).iloc[period:].to_numpy()
    np.testing.assert_allclose(actual, expected, rtol=1e-10)


def test_rsi_extremes():
    assert ind.rsi(pd.Series(np.arange(1.0, 40.0)), 14).iloc[-1] == pytest.approx(100.0)
    assert ind.rsi(pd.Series(np.arange(40.0, 1.0, -1)), 14).iloc[-1] == pytest.approx(0.0)
    assert ind.rsi(pd.Series([5.0] * 40), 14).iloc[-1] == pytest.approx(50.0)


def test_atr_of_constant_range_bars():
    df = pd.DataFrame({"open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 1.0}, index=range(30))
    assert ind.atr(df, 14).iloc[-1] == pytest.approx(2.0)


def test_bollinger_and_donchian():
    flat = pd.Series([10.0] * 25)
    bands = ind.bollinger(flat, 20, 2.0).iloc[-1]
    assert bands["upper"] == bands["lower"] == bands["mid"] == pytest.approx(10.0)

    df = make_ohlcv([1, 2, 3, 4, 5, 4, 3], spread=0.0)
    channel = ind.donchian(df, 3)
    assert channel["upper"].iloc[-1] == 5.0
    assert channel["lower"].iloc[-1] == 3.0


def test_percent_b_places_the_close_within_the_bands():
    assert ind.percent_b(pd.Series([1.0, 3.0, 2.0]), 3, 1.0).iloc[-1] == pytest.approx(0.5)
    close = random_walk()["close"]
    bands = ind.bollinger(close, 20, 2.0)
    expected = (close - bands["lower"]) / (bands["upper"] - bands["lower"])
    pd.testing.assert_series_equal(ind.percent_b(close, 20, 2.0), expected)
    # Bands without width have no %b.
    assert np.isnan(ind.percent_b(pd.Series([10.0] * 25), 20, 2.0).iloc[-1])


def test_internal_bar_strength():
    df = pd.DataFrame({"high": [12.0, 12.0, 12.0, 10.0], "low": [10.0, 10.0, 10.0, 10.0], "close": [10.0, 10.5, 12.0, 10.0]})
    strength = ind.internal_bar_strength(df)
    assert strength.iloc[:3].tolist() == [0.0, 0.25, 1.0]
    # A bar without range has no IBS.
    assert np.isnan(strength.iloc[3])


def test_adx_detects_a_strong_uptrend():
    frame = ind.adx(make_ohlcv(np.linspace(100, 200, 120)), 14).iloc[-1]
    assert frame["plus_di"] > frame["minus_di"]
    assert frame["adx"] > 40


def test_supertrend_follows_trend_changes():
    close = np.r_[np.linspace(100, 150, 80), np.linspace(150, 90, 80)]
    trend = ind.supertrend(make_ohlcv(close), 10, 3.0)["direction"]
    assert trend.iloc[75] == 1.0
    assert trend.iloc[-1] == -1.0


def test_relative_volume_and_macd_shape():
    volume = pd.Series([100.0] * 25 + [300.0])
    assert ind.relative_volume(volume, 20).iloc[-1] == pytest.approx(3.0)
    frame = ind.macd(random_walk(200)["close"])
    assert list(frame.columns) == ["macd", "signal", "hist"]
    np.testing.assert_allclose(frame["hist"].dropna(), (frame["macd"] - frame["signal"]).dropna())
