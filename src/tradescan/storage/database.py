"""One SQLite file holds what the server keeps between runs: the pinned runs and the trade journal.

Every operation opens its own connection, so the API's worker threads never share one. The schema version is
SQLite's `user_version`: a change to the schema appends a migration to `_MIGRATIONS` and never edits one, so a
file written by an older version is upgraded when it is opened.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

MAX_JSON_BYTES = 2_000_000  # a ten-year daily equity curve is about 60 kB

_MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE pinned_runs (
        id TEXT PRIMARY KEY,
        slot INTEGER NOT NULL UNIQUE,
        name TEXT NOT NULL,
        hidden INTEGER NOT NULL,
        pinned_at TEXT NOT NULL,
        format INTEGER NOT NULL,
        snapshot TEXT NOT NULL
    );
    CREATE TABLE journal_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        direction TEXT NOT NULL,
        opened TEXT NOT NULL,
        entry_price REAL NOT NULL,
        quantity REAL NOT NULL,
        stop REAL,
        closed TEXT,
        exit_price REAL,
        fees REAL NOT NULL,
        notes TEXT NOT NULL,
        run_format INTEGER,
        run_snapshot TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
)


class NotFoundError(LookupError):
    """No stored item has the id asked for."""


class ConflictError(Exception):
    """The change clashes with what is stored, e.g. a slot another run already holds."""


class Database:
    """A SQLite file, created with its parent directory on first use."""

    def __init__(self, path: Path) -> None:
        self._path: Path | None = path
        self._target = str(path)
        self._uri = False
        self._keeper: sqlite3.Connection | None = None
        self._migrated = False
        self._lock = threading.Lock()

    @classmethod
    def in_memory(cls) -> Database:
        """A database that lasts as long as this object, for tests and for an app given no file."""
        database = cls(Path(":memory:"))
        database._path = None
        database._target = f"file:tradescan-{uuid.uuid4().hex}?mode=memory&cache=shared"
        database._uri = True
        # A shared in-memory database is dropped when its last connection closes.
        database._keeper = sqlite3.connect(database._target, uri=True, check_same_thread=False)
        return database

    @property
    def location(self) -> str:
        return str(self._path) if self._path is not None else "memory"

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """A connection whose changes are committed when the block ends and rolled back when it raises."""
        self.migrate()
        connection = self._open()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def migrate(self) -> None:
        """Create or upgrade the schema; a ValueError when the file is not a tradescan database or is newer."""
        if self._migrated:
            return
        with self._lock:
            if self._migrated:
                return
            if self._path is not None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
            connection = self._open()
            try:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version > len(_MIGRATIONS):
                    raise ValueError(f"{self.location} was written by a newer tradescan (schema {version})")
                for number, script in enumerate(_MIGRATIONS[version:], start=version + 1):
                    connection.executescript(f"BEGIN; {script} PRAGMA user_version = {number}; COMMIT;")
            except sqlite3.DatabaseError as error:
                raise ValueError(f"{self.location} is not a tradescan database ({error})") from error
            finally:
                connection.close()
            self._migrated = True

    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._target, uri=self._uri, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection


def encode_json(value: dict[str, Any], what: str) -> str:
    """`value` as compact JSON; a ValueError when it is larger than MAX_JSON_BYTES."""
    text = json.dumps(value, separators=(",", ":"), allow_nan=False)
    if len(text.encode()) > MAX_JSON_BYTES:
        raise ValueError(f"{what} is larger than {MAX_JSON_BYTES // 1_000_000} MB")
    return text
