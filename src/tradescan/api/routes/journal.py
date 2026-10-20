"""The trade journal: real trades with notes and the pinned run that suggested them."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from tradescan.api.context import ApiContext
from tradescan.api.mappers import journal_out, journal_trade_out
from tradescan.api.schemas.common import ErrorOut
from tradescan.api.schemas.journal import JournalOut, JournalTradeIn, JournalTradeOut
from tradescan.journal import SuggestedBy, TradeEntry

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorOut, "description": "No trade in the journal has this id"}
}


def _trade_entry(body: JournalTradeIn) -> TradeEntry:
    run = body.run
    return TradeEntry(
        ticker=body.ticker.strip(),
        direction=body.direction,
        opened=body.opened,
        entry_price=body.entry_price,
        quantity=body.quantity,
        stop=body.stop,
        closed=body.closed,
        exit_price=body.exit_price,
        fees=body.fees,
        notes=body.notes,
        run=SuggestedBy(format=run.format, snapshot=run.snapshot) if run else None,
    )


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["journal"])
    journal = context.journal

    @router.get("/journal", response_model=JournalOut)
    def list_trades() -> JournalOut:
        return journal_out(journal.trades())

    @router.post("/journal/trades", response_model=JournalTradeOut, status_code=201)
    def log_trade(body: JournalTradeIn) -> JournalTradeOut:
        return journal_trade_out(journal.add(_trade_entry(body)))

    @router.put("/journal/trades/{trade_id}", response_model=JournalTradeOut, responses=_NOT_FOUND)
    def replace_trade(trade_id: int, body: JournalTradeIn) -> JournalTradeOut:
        return journal_trade_out(journal.replace(trade_id, _trade_entry(body)))

    @router.delete("/journal/trades/{trade_id}", status_code=204, responses=_NOT_FOUND)
    def delete_trade(trade_id: int) -> None:
        journal.remove(trade_id)

    return router
