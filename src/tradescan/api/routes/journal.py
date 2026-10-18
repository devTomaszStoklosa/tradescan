"""The trade journal: real trades with notes and the pinned run that suggested them."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api import schemas
from tradescan.api.context import ApiContext
from tradescan.api.mappers import journal_out, journal_trade_out
from tradescan.journal import SuggestedBy, TradeEntry

_NOT_FOUND = {404: {"model": schemas.ErrorOut, "description": "No trade in the journal has this id"}}


def _trade_entry(body: schemas.JournalTradeIn) -> TradeEntry:
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

    @router.get("/journal", response_model=schemas.JournalOut)
    def list_trades() -> schemas.JournalOut:
        return journal_out(journal.trades())

    @router.post("/journal/trades", response_model=schemas.JournalTradeOut, status_code=201)
    def log_trade(body: schemas.JournalTradeIn) -> schemas.JournalTradeOut:
        return journal_trade_out(journal.add(_trade_entry(body)))

    @router.put("/journal/trades/{trade_id}", response_model=schemas.JournalTradeOut, responses=_NOT_FOUND)
    def replace_trade(trade_id: int, body: schemas.JournalTradeIn) -> schemas.JournalTradeOut:
        return journal_trade_out(journal.replace(trade_id, _trade_entry(body)))

    @router.delete("/journal/trades/{trade_id}", status_code=204, responses=_NOT_FOUND)
    def delete_trade(trade_id: int) -> None:
        journal.remove(trade_id)

    return router
