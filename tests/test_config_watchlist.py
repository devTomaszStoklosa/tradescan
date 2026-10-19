from pathlib import Path

import pytest

from tradescan.config import Settings, load_settings
from tradescan.watchlist import from_tickers, load_watchlist, parse_watchlist

PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "config"


def test_parse_watchlist_reads_tickers_comments_and_benchmark():
    text = "# my list\n# benchmark: wig20.wa\npko.wa, PZU.WA  # banks\nCDR.WA PKO.WA\n"
    watchlist = parse_watchlist("pl", text)
    assert watchlist.tickers == ("PKO.WA", "PZU.WA", "CDR.WA")
    assert watchlist.benchmark == "WIG20.WA"


def test_from_tickers_splits_commas():
    assert from_tickers("aapl, msft").tickers == ("AAPL", "MSFT")


def test_bundled_watchlists_load():
    for name in ("us_large", "wig20", "etf", "crypto"):
        watchlist = load_watchlist(name, PROJECT_CONFIG / "watchlists")
        assert watchlist.tickers
        assert watchlist.benchmark


def test_missing_watchlist_lists_available(tmp_path):
    (tmp_path / "mine.txt").write_text("AAA")
    with pytest.raises(FileNotFoundError, match="mine"):
        load_watchlist("other", tmp_path)


def test_bundled_settings_match_defaults_where_unchanged():
    settings = load_settings(PROJECT_CONFIG / "settings.toml")
    assert settings.risk.targets_r == (2.0, 3.0)
    assert settings.scoring.family_weights["breakout"] == 1.5
    assert load_settings(Path("does-not-exist.toml")) == Settings()


def test_unknown_keys_are_rejected(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text("[risk]\natr_multt = 3\n")
    with pytest.raises(ValueError, match="atr_multt"):
        load_settings(path)
