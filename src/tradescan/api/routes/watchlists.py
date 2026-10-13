"""Bundled watchlists."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api import schemas
from tradescan.api.context import ApiContext
from tradescan.api.mappers import watchlist_out
from tradescan.watchlist import load_watchlist


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["watchlists"])

    @router.get("/watchlists", response_model=list[schemas.WatchlistOut])
    def list_watchlists() -> list[schemas.WatchlistOut]:
        return [watchlist_out(load_watchlist(name, context.watchlists_dir)) for name in context.watchlist_names()]

    return router
