"""The trade journal's trades in the database."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, date, datetime

from tradescan.journal import JournalTrade, SuggestedBy, TradeEntry
from tradescan.signals.base import Direction
from tradescan.storage.database import Database, NotFound, encode_json

_COLUMNS = (
    "ticker", "direction", "opened", "entry_price", "quantity", "stop", "closed", "exit_price", "fees", "notes",
    "run_format", "run_snapshot",
)  # fmt: skip


def _now() -> datetime:
    return datetime.now(UTC)


class TradeJournal:
    def __init__(self, database: Database, clock: Callable[[], datetime] = _now) -> None:
        self._database = database
        self._clock = clock

    def trades(self) -> list[JournalTrade]:
        """Every trade, the latest opened first."""
        with self._database.connect() as connection:
            rows = connection.execute("SELECT * FROM journal_trades ORDER BY opened DESC, id DESC").fetchall()
        return [_trade(row) for row in rows]

    def add(self, entry: TradeEntry) -> JournalTrade:
        now = self._timestamp()
        names = ", ".join((*_COLUMNS, "created_at", "updated_at"))
        marks = ", ".join("?" * (len(_COLUMNS) + 2))
        with self._database.connect() as connection:
            cursor = connection.execute(
                f"INSERT INTO journal_trades ({names}) VALUES ({marks})", (*_values(entry), now, now)
            )
        return JournalTrade(id=int(cursor.lastrowid or 0), entry=entry, created_at=now, updated_at=now)

    def replace(self, trade_id: int, entry: TradeEntry) -> JournalTrade:
        """The trade with every field of `entry`; a NotFound when there is no such trade."""
        assignments = ", ".join(f"{name} = ?" for name in (*_COLUMNS, "updated_at"))
        with self._database.connect() as connection:
            connection.execute(
                f"UPDATE journal_trades SET {assignments} WHERE id = ?", (*_values(entry), self._timestamp(), trade_id)
            )
            row = connection.execute("SELECT * FROM journal_trades WHERE id = ?", (trade_id,)).fetchone()
        if row is None:
            raise NotFound(f"No trade {trade_id} in the journal")
        return _trade(row)

    def remove(self, trade_id: int) -> None:
        with self._database.connect() as connection:
            if not connection.execute("DELETE FROM journal_trades WHERE id = ?", (trade_id,)).rowcount:
                raise NotFound(f"No trade {trade_id} in the journal")

    def _timestamp(self) -> str:
        return self._clock().isoformat(timespec="seconds")


def _values(entry: TradeEntry) -> tuple[object, ...]:
    run = entry.run
    return (
        entry.ticker,
        entry.direction.value,
        entry.opened.isoformat(),
        entry.entry_price,
        entry.quantity,
        entry.stop,
        entry.closed.isoformat() if entry.closed else None,
        entry.exit_price,
        entry.fees,
        entry.notes,
        run.format if run else None,
        encode_json(run.snapshot, "The suggesting run") if run else None,
    )


def _trade(row: sqlite3.Row) -> JournalTrade:
    snapshot = row["run_snapshot"]
    run = SuggestedBy(format=row["run_format"], snapshot=json.loads(snapshot)) if snapshot else None
    entry = TradeEntry(
        ticker=row["ticker"],
        direction=Direction(row["direction"]),
        opened=date.fromisoformat(row["opened"]),
        entry_price=row["entry_price"],
        quantity=row["quantity"],
        stop=row["stop"],
        closed=date.fromisoformat(row["closed"]) if row["closed"] else None,
        exit_price=row["exit_price"],
        fees=row["fees"],
        notes=row["notes"],
        run=run,
    )
    return JournalTrade(id=row["id"], entry=entry, created_at=row["created_at"], updated_at=row["updated_at"])
