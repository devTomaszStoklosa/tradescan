import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from tradescan.journal import SuggestedBy, TradeEntry
from tradescan.signals.base import Direction
from tradescan.storage.database import ConflictError, Database, NotFoundError
from tradescan.storage.runs import PinnedRun, PinnedRunStore
from tradescan.storage.trades import TradeJournal

SNAPSHOT = {"kind": "backtest", "ticker": "SPY", "equity": {"time": ["2026-01-02"], "value": [100000.0]}}


def pinned(slot: int, run_id: str | None = None, **changes) -> PinnedRun:
    values = {
        "id": run_id or f"run-{slot}",
        "slot": slot,
        "name": f"run {slot}",
        "hidden": False,
        "pinned_at": "2026-10-18T09:00:00.000Z",
        "format": 7,
        "snapshot": SNAPSHOT,
    }
    return PinnedRun(**(values | changes))


def entry(**changes) -> TradeEntry:
    values = {
        "ticker": "SPY",
        "direction": Direction.LONG,
        "opened": date(2026, 3, 2),
        "entry_price": 500.0,
        "quantity": 2.0,
    }
    return TradeEntry(**(values | changes))


@pytest.fixture
def database(tmp_path: Path) -> Database:
    return Database(tmp_path / "data" / "tradescan.db")


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


# --- Database ---------------------------------------------------------------------------------------


def test_the_file_and_its_directory_are_created_on_first_use(database, tmp_path):
    assert not (tmp_path / "data").exists()
    assert PinnedRunStore(database).runs() == []
    assert (tmp_path / "data" / "tradescan.db").is_file()


def test_the_schema_version_is_recorded_and_kept(tmp_path):
    path = tmp_path / "tradescan.db"
    PinnedRunStore(Database(path)).add(pinned(1))
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    assert [run.id for run in PinnedRunStore(Database(path)).runs()] == ["run-1"]


def test_a_newer_schema_is_refused(tmp_path):
    path = tmp_path / "tradescan.db"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 99")
    with pytest.raises(ValueError, match="newer tradescan"):
        Database(path).migrate()


def test_a_file_that_is_not_a_database_is_refused(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not a database " * 100)
    with pytest.raises(ValueError, match="not a tradescan database"):
        Database(path).migrate()


def test_an_in_memory_database_keeps_its_data_until_it_is_dropped():
    first, second = Database.in_memory(), Database.in_memory()
    PinnedRunStore(first).add(pinned(1))
    assert len(PinnedRunStore(first).runs()) == 1
    assert PinnedRunStore(second).runs() == []
    assert first.location == "memory"


# --- Pinned runs ------------------------------------------------------------------------------------


def test_runs_are_listed_by_slot_with_their_snapshot(database):
    store = PinnedRunStore(database)
    store.add(pinned(3))
    store.add(pinned(1, hidden=True))
    runs = store.runs()
    assert [run.slot for run in runs] == [1, 3]
    assert runs[0] == pinned(1, hidden=True)


def test_a_taken_slot_or_a_pinned_id_is_a_conflict(database):
    store = PinnedRunStore(database)
    store.add(pinned(1))
    with pytest.raises(ConflictError, match="Slot 1 is taken"):
        store.add(pinned(1, run_id="other"))
    with pytest.raises(ConflictError, match="already pinned"):
        store.add(pinned(2, run_id="run-1"))
    assert [run.id for run in store.runs()] == ["run-1"]


@pytest.mark.parametrize("slot", [0, 9])
def test_a_slot_outside_one_to_eight_is_refused(slot):
    with pytest.raises(ValueError, match="slot is 1 to 8"):
        pinned(slot)


def test_a_snapshot_above_the_size_cap_is_refused(database):
    with pytest.raises(ValueError, match="larger than 2 MB"):
        PinnedRunStore(database).add(pinned(1, snapshot={"notes": "x" * 2_000_001}))


def test_a_run_is_renamed_hidden_and_removed(database):
    store = PinnedRunStore(database)
    store.add(pinned(1))
    assert store.update("run-1", name="baseline").name == "baseline"
    hidden = store.update("run-1", hidden=True)
    assert (hidden.name, hidden.hidden) == ("baseline", True)
    store.remove("run-1")
    assert store.runs() == []
    with pytest.raises(NotFoundError):
        store.remove("run-1")
    with pytest.raises(NotFoundError):
        store.update("run-1", name="gone")


def test_clear_removes_every_run(database):
    store = PinnedRunStore(database)
    for slot in (1, 2, 3):
        store.add(pinned(slot))
    store.clear()
    assert store.runs() == []


# --- Journal ----------------------------------------------------------------------------------------


def test_trades_keep_every_field_and_the_suggesting_run(database):
    journal = TradeJournal(database, clock=Clock())
    logged = entry(
        stop=490.0,
        closed=date(2026, 3, 9),
        exit_price=520.0,
        fees=1.5,
        notes="Gap up\nheld",
        run=SuggestedBy(7, SNAPSHOT),
    )
    added = journal.add(logged)
    assert (added.created_at, added.updated_at) == ("2026-10-18T09:00:00+00:00", "2026-10-18T09:00:00+00:00")
    [stored] = TradeJournal(database).trades()
    assert stored == added
    assert stored.entry == logged


def test_trades_are_listed_latest_opened_first(database):
    journal = TradeJournal(database)
    first = journal.add(entry(opened=date(2026, 3, 2)))
    later = journal.add(entry(opened=date(2026, 4, 1)))
    same_day = journal.add(entry(opened=date(2026, 3, 2), ticker="QQQ"))
    assert [trade.id for trade in journal.trades()] == [later.id, same_day.id, first.id]


def test_a_trade_is_replaced_with_a_new_update_time(database):
    clock = Clock()
    journal = TradeJournal(database, clock=clock)
    added = journal.add(entry(run=SuggestedBy(7, SNAPSHOT)))
    clock.now = datetime(2026, 10, 19, 15, 30, tzinfo=UTC)
    closed = entry(closed=date(2026, 3, 9), exit_price=520.0, notes="Target hit")
    replaced = journal.replace(added.id, closed)
    assert replaced.entry == closed
    assert replaced.entry.run is None
    assert (replaced.created_at, replaced.updated_at) == (added.created_at, "2026-10-19T15:30:00+00:00")
    with pytest.raises(NotFoundError):
        journal.replace(added.id + 1, closed)


def test_a_trade_is_removed(database):
    journal = TradeJournal(database)
    added = journal.add(entry())
    journal.remove(added.id)
    assert journal.trades() == []
    with pytest.raises(NotFoundError):
        journal.remove(added.id)
