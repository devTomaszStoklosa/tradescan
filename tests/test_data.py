import pandas as pd
import pytest

from tests.synthetic import FakeProvider, make_ohlcv
from tradescan.data.cache import CachedProvider
from tradescan.data.schema import normalize_ohlcv
from tradescan.data.yfinance_provider import YFinanceProvider, split_download


def _yahoo_frame(tickers, ticker_first=True):
    base = make_ohlcv([10.0, 11.0, 12.0]).rename(columns=str.capitalize)
    parts = {ticker: base * (number + 1) for number, ticker in enumerate(tickers)}
    frame = pd.concat(parts, axis=1)
    return frame if ticker_first else frame.swaplevel(0, 1, axis=1)


def test_normalize_ohlcv_cleans_yahoo_style_frames():
    raw = make_ohlcv([1.0, 2.0, 3.0]).rename(columns=str.upper)
    raw.index = raw.index.tz_localize("America/New_York")
    raw = pd.concat([raw, raw.iloc[[1]]])
    raw.iloc[0, 3] = float("nan")
    clean = normalize_ohlcv(raw)
    assert list(clean.columns) == ["open", "high", "low", "close", "volume"]
    assert clean.index.tz is None
    assert clean.index.is_monotonic_increasing
    assert clean.index.is_unique
    assert len(clean) == 2


def test_normalize_rejects_missing_columns():
    with pytest.raises(ValueError, match="volume"):
        normalize_ohlcv(make_ohlcv([1.0, 2.0]).drop(columns="volume"))


@pytest.mark.parametrize("ticker_first", [True, False])
def test_split_download_handles_both_multiindex_layouts(ticker_first):
    frames = split_download(_yahoo_frame(["AAA", "BBB"], ticker_first), ["AAA", "BBB", "MISSING"])
    assert set(frames) == {"AAA", "BBB"}
    assert frames["BBB"]["close"].iloc[-1] == pytest.approx(24.0)


def test_split_download_flat_single_ticker():
    raw = make_ohlcv([1.0, 2.0]).rename(columns=str.capitalize)
    assert list(split_download(raw, ["AAA"])) == ["AAA"]


def test_yfinance_provider_batches_one_request():
    calls = []

    def fake_download(tickers, **kwargs):
        calls.append((tickers, kwargs))
        return _yahoo_frame(tickers)

    frames = YFinanceProvider(fake_download).history(["AAA", "BBB"], "1y", "1d")
    assert set(frames) == {"AAA", "BBB"}
    assert len(calls) == 1
    assert calls[0][1]["auto_adjust"] is True
    assert calls[0][1]["period"] == "1y"


def test_cache_serves_fresh_files_and_refetches_stale(tmp_path):
    now = [1_000_000.0]
    inner = FakeProvider({"AAA": make_ohlcv([1.0, 2.0]), "^IDX": make_ohlcv([3.0, 4.0])})
    cache = CachedProvider(inner, tmp_path, ttl_seconds=3600, clock=lambda: now[0])

    first = cache.history(["AAA", "^IDX"], "1y", "1d")
    assert set(first) == {"AAA", "^IDX"}
    pd.testing.assert_frame_equal(first["AAA"], inner.frames["AAA"], check_freq=False)

    now[0] = (tmp_path / "1d" / "1y" / "AAA.parquet").stat().st_mtime + 10
    cache.history(["AAA", "^IDX"], "1y", "1d")
    assert len(inner.calls) == 1

    now[0] += 7200
    cache.history(["AAA"], "1y", "1d")
    assert inner.calls[-1] == (("AAA",), "1y", "1d")
