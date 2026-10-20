"""Pinned runs: the UI's frozen snapshots of a backtest or portfolio run, kept for Compare.

The UI owns the snapshot's format: it stores its runs-file version next to the snapshot and upgrades older
ones when it reads them. The server checks only what it keeps in columns (the id, the slot and the name) and
the snapshot's size.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from tradescan.storage.database import ConflictError, Database, NotFoundError, encode_json

MAX_PINNED_RUNS = 8  # the UI's MAX_RUNS: one chart and the run palette stay legible up to this many


@dataclass(frozen=True)
class PinnedRun:
    id: str
    slot: int  # number and colour in Compare, 1 to MAX_PINNED_RUNS
    name: str
    hidden: bool
    pinned_at: str
    format: int  # the UI's runs-file version the snapshot was written in
    snapshot: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("A pinned run needs an id")
        if not 1 <= self.slot <= MAX_PINNED_RUNS:
            raise ValueError(f"A pinned run's slot is 1 to {MAX_PINNED_RUNS}, not {self.slot}")


class PinnedRunStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    def runs(self) -> list[PinnedRun]:
        """Every pinned run, by slot."""
        with self._database.connect() as connection:
            rows = connection.execute("SELECT * FROM pinned_runs ORDER BY slot").fetchall()
        return [_run(row) for row in rows]

    def add(self, run: PinnedRun) -> PinnedRun:
        """Pin `run`; a ConflictError when its id is already pinned or another run holds its slot."""
        snapshot = encode_json(run.snapshot, "The run")
        with self._database.connect() as connection:
            if connection.execute("SELECT 1 FROM pinned_runs WHERE id = ?", (run.id,)).fetchone():
                raise ConflictError(f"Run {run.id} is already pinned")
            try:
                connection.execute(
                    "INSERT INTO pinned_runs (id, slot, name, hidden, pinned_at, format, snapshot)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (run.id, run.slot, run.name, int(run.hidden), run.pinned_at, run.format, snapshot),
                )
            except sqlite3.IntegrityError as error:
                raise ConflictError(f"Slot {run.slot} is taken by another pinned run") from error
        return run

    def update(self, run_id: str, *, name: str | None = None, hidden: bool | None = None) -> PinnedRun:
        """Rename, hide or show a pinned run; what is None stays as it is."""
        with self._database.connect() as connection:
            if name is not None:
                connection.execute("UPDATE pinned_runs SET name = ? WHERE id = ?", (name, run_id))
            if hidden is not None:
                connection.execute("UPDATE pinned_runs SET hidden = ? WHERE id = ?", (int(hidden), run_id))
            row = connection.execute("SELECT * FROM pinned_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"No pinned run {run_id}")
        return _run(row)

    def remove(self, run_id: str) -> None:
        with self._database.connect() as connection:
            if not connection.execute("DELETE FROM pinned_runs WHERE id = ?", (run_id,)).rowcount:
                raise NotFoundError(f"No pinned run {run_id}")

    def clear(self) -> None:
        with self._database.connect() as connection:
            connection.execute("DELETE FROM pinned_runs")


def _run(row: sqlite3.Row) -> PinnedRun:
    return PinnedRun(
        id=row["id"],
        slot=row["slot"],
        name=row["name"],
        hidden=bool(row["hidden"]),
        pinned_at=row["pinned_at"],
        format=row["format"],
        snapshot=json.loads(row["snapshot"]),
    )
