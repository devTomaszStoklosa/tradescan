"""Dependencies shared by the API routes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from tradescan.api.schemas import SignalFilterIn, UniverseIn
from tradescan.config import Settings
from tradescan.scoring import Scorer
from tradescan.services.composition import UseCases
from tradescan.services.market_data import SignalFilter
from tradescan.signals.registry import SignalRegistry
from tradescan.storage.runs import PinnedRunStore
from tradescan.storage.trades import TradeJournal
from tradescan.watchlist import Watchlist, available_watchlists, from_tickers, load_watchlist


@dataclass(frozen=True)
class ApiContext:
    settings: Settings
    use_cases: UseCases
    registry: SignalRegistry
    scorer: Scorer
    watchlists_dir: Path
    runs: PinnedRunStore
    journal: TradeJournal

    def watchlist_names(self) -> list[str]:
        return available_watchlists(self.watchlists_dir)

    def universe(self, request: UniverseIn) -> Watchlist:
        if request.tickers:
            return from_tickers(",".join(request.tickers))
        # Only names from the watchlists dir: `load_watchlist` also accepts file paths, which the API must not.
        names = self.watchlist_names()
        if request.watchlist not in names:
            raise HTTPException(status_code=404, detail=f"Unknown watchlist. Available: {', '.join(names) or 'none'}")
        return load_watchlist(str(request.watchlist), self.watchlists_dir)

    def check_signals(self, names: Sequence[str]) -> None:
        unknown = sorted(set(names) - set(self.registry.names()))
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown signal(s): {', '.join(unknown)}")

    def signal_filter(self, request: SignalFilterIn) -> SignalFilter:
        self.check_signals(request.signals)
        return SignalFilter(names=tuple(request.signals), families=tuple(request.families), direction=request.direction)
