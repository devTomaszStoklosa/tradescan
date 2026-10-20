"""Map watchlists to the models of GET /api/watchlists."""

from __future__ import annotations

from tradescan.api.schemas.watchlists import WatchlistOut
from tradescan.watchlist import Watchlist


def watchlist_out(watchlist: Watchlist) -> WatchlistOut:
    return WatchlistOut(name=watchlist.name, tickers=list(watchlist.tickers), benchmark=watchlist.benchmark)
