from datetime import date

import pytest

from tradescan.journal import TradeEntry, summarize
from tradescan.signals.base import Direction

OPENED = date(2026, 3, 2)
CLOSED = date(2026, 3, 20)


def trade(**changes) -> TradeEntry:
    values = {"ticker": "AAPL", "direction": Direction.LONG, "opened": OPENED, "entry_price": 100.0, "quantity": 10.0}
    return TradeEntry(**(values | changes))


def test_a_long_trade_earns_when_the_price_rises():
    entry = trade(stop=95.0, closed=CLOSED, exit_price=110.0, fees=2.0)
    assert not entry.is_open
    assert entry.risk == 50.0
    assert entry.profit == 98.0
    assert entry.return_pct == pytest.approx(9.8)
    assert entry.r_multiple == pytest.approx(1.96)


def test_a_short_trade_earns_when_the_price_falls():
    entry = trade(direction=Direction.SHORT, stop=104.0, closed=CLOSED, exit_price=92.0)
    assert entry.profit == 80.0
    assert entry.r_multiple == pytest.approx(2.0)
    loser = trade(direction=Direction.SHORT, stop=104.0, closed=CLOSED, exit_price=106.0)
    assert loser.profit == -60.0
    assert loser.r_multiple == pytest.approx(-1.5)


def test_an_open_trade_has_no_result_yet():
    entry = trade(stop=95.0)
    assert entry.is_open
    assert (entry.profit, entry.return_pct, entry.r_multiple) == (None, None, None)
    assert entry.risk == 50.0


def test_a_trade_without_a_stop_has_no_r_multiple():
    entry = trade(closed=CLOSED, exit_price=105.0)
    assert entry.risk is None
    assert entry.r_multiple is None
    assert entry.profit == 50.0


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"ticker": " "}, "needs a ticker"),
        ({"entry_price": 0.0}, "above 0"),
        ({"quantity": -1.0}, "above 0"),
        ({"fees": -0.5}, "negative"),
        ({"stop": 100.0}, "below the entry"),
        ({"direction": Direction.SHORT, "stop": 99.0}, "above the entry"),
        ({"closed": CLOSED}, "both its date and its price"),
        ({"exit_price": 101.0}, "both its date and its price"),
        ({"closed": CLOSED, "exit_price": 0.0}, "exit price must be above 0"),
        ({"closed": date(2026, 3, 1), "exit_price": 101.0}, "close before it opened"),
    ],
)
def test_invalid_trades_are_rejected(changes, message):
    with pytest.raises(ValueError, match=message):
        trade(**changes)


def test_the_summary_adds_up_r_and_percentages_of_closed_trades():
    entries = [
        trade(stop=95.0, closed=CLOSED, exit_price=110.0),  # +2R, +10%
        trade(stop=95.0, closed=CLOSED, exit_price=95.0),  # -1R, -5%
        trade(closed=CLOSED, exit_price=103.0),  # no stop: +3%, no R
        trade(stop=95.0),  # open
    ]
    summary = summarize(entries)
    assert (summary.open_trades, summary.closed_trades, summary.r_trades) == (1, 3, 2)
    assert summary.win_rate_pct == pytest.approx(200 / 3)
    assert summary.average_return_pct == pytest.approx(8 / 3)
    assert summary.average_r == pytest.approx(0.5)
    assert summary.total_r == pytest.approx(1.0)


def test_an_empty_summary_has_no_averages():
    summary = summarize([trade()])
    assert (summary.open_trades, summary.closed_trades) == (1, 0)
    assert (summary.win_rate_pct, summary.average_return_pct, summary.average_r, summary.total_r) == (None,) * 4
