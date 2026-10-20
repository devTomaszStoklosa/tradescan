"""Models of GET /api/watchlists."""

from __future__ import annotations

from pydantic import BaseModel


class WatchlistOut(BaseModel):
    name: str
    tickers: list[str]
    benchmark: str | None
