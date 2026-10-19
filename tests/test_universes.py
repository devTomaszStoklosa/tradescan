from datetime import date
from pathlib import Path

import pytest

from tradescan import cli
from tradescan.universes import SOURCES, UniverseSource, parse_constituents, update_universe, yahoo_symbol
from tradescan.watchlist import load_watchlist

SOURCE = UniverseSource(
    name="demo", title="Demo 5", url="https://example.test/demo", column="Symbol", benchmark="SPY", min_members=3
)


def _page(symbols: list[str]) -> str:
    rows = "".join(f"<tr><td>{symbol}</td><td>Company {symbol}</td></tr>" for symbol in symbols)
    other = "<table><tr><th>Year</th><th>Close</th></tr><tr><td>2024</td><td>1</td></tr></table>"
    return f"<html><body>{other}<table><tr><th>Symbol</th><th>Security</th></tr>{rows}</table></body></html>"


def test_yahoo_symbols_use_dashes_for_share_classes():
    assert yahoo_symbol(" brk.b ") == "BRK-B"
    assert yahoo_symbol("AAPL") == "AAPL"


def test_parse_finds_the_symbol_table_and_validates_size():
    assert parse_constituents(_page(["AAPL", "BRK.B", "MSFT", "AAPL"]), SOURCE) == ("AAPL", "BRK-B", "MSFT")
    with pytest.raises(ValueError, match="only 2 members"):
        parse_constituents(_page(["AAPL", "MSFT"]), SOURCE)
    with pytest.raises(ValueError, match="no table"):
        parse_constituents("<table><tr><th>Ticker</th></tr><tr><td>X</td></tr></table>", SOURCE)


def test_update_writes_a_watchlist_and_reports_changes(tmp_path: Path):
    first = update_universe(
        SOURCE, tmp_path, fetch=lambda url: _page(["AAPL", "MSFT", "NVDA"]), today=lambda: date(2026, 10, 13)
    )
    assert first.created and first.added == ()
    watchlist = load_watchlist("demo", tmp_path)
    assert watchlist.tickers == ("AAPL", "MSFT", "NVDA") and watchlist.benchmark == "SPY"
    assert "2026-10-13" in (tmp_path / "demo.txt").read_text()

    second = update_universe(SOURCE, tmp_path, fetch=lambda url: _page(["AAPL", "MSFT", "AMD", "BRK.B"]))
    assert not second.created
    assert (second.added, second.removed) == (("AMD", "BRK-B"), ("NVDA",))


def test_failed_update_keeps_the_existing_file(tmp_path: Path):
    (tmp_path / "demo.txt").write_text("# benchmark: SPY\nAAPL MSFT NVDA\n")
    with pytest.raises(ValueError):
        update_universe(SOURCE, tmp_path, fetch=lambda url: _page(["AAPL"]))
    assert load_watchlist("demo", tmp_path).tickers == ("AAPL", "MSFT", "NVDA")


def test_bundled_index_universes_are_present():
    directory = Path(__file__).resolve().parents[1] / "config" / "watchlists"
    for source in SOURCES:
        watchlist = load_watchlist(source.name, directory)
        assert len(watchlist.tickers) >= source.min_members
        assert watchlist.benchmark == source.benchmark
        assert all("." not in ticker for ticker in watchlist.tickers)


def test_cli_rejects_unknown_universe(tmp_path: Path):
    assert cli.main(["--watchlists-dir", str(tmp_path), "update-universes", "--only", "ftse"]) == 2
