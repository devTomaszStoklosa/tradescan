"""Map the trade journal."""

from __future__ import annotations

from collections.abc import Sequence

from tradescan.api.mappers.common import finite
from tradescan.api.schemas.journal import JournalOut, JournalSummaryOut, JournalTradeOut, SuggestingRun
from tradescan.journal import JournalTrade, summarize


def journal_trade_out(trade: JournalTrade) -> JournalTradeOut:
    entry = trade.entry
    run = entry.run
    return JournalTradeOut(
        id=trade.id,
        ticker=entry.ticker,
        direction=entry.direction,
        opened=entry.opened,
        entry_price=entry.entry_price,
        quantity=entry.quantity,
        stop=entry.stop,
        closed=entry.closed,
        exit_price=entry.exit_price,
        fees=entry.fees,
        notes=entry.notes,
        run=SuggestingRun(format=run.format, snapshot=run.snapshot) if run else None,
        created_at=trade.created_at,
        updated_at=trade.updated_at,
        is_open=entry.is_open,
        risk=finite(entry.risk),
        profit=finite(entry.profit),
        return_pct=finite(entry.return_pct),
        r_multiple=finite(entry.r_multiple),
    )


def journal_out(trades: Sequence[JournalTrade]) -> JournalOut:
    summary = summarize([trade.entry for trade in trades])
    return JournalOut(
        trades=[journal_trade_out(trade) for trade in trades],
        summary=JournalSummaryOut(
            open_trades=summary.open_trades,
            closed_trades=summary.closed_trades,
            win_rate_pct=finite(summary.win_rate_pct),
            average_return_pct=finite(summary.average_return_pct),
            r_trades=summary.r_trades,
            average_r=finite(summary.average_r),
            total_r=finite(summary.total_r),
        ),
    )
