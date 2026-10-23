# Data, configuration and storage

Everything tradescan reads or writes outside the code: market data and its cache, watchlists, the settings
file, the SQLite database, and exports.

## Market data

**Contract.** A data source implements the `DataProvider` protocol
([`data/provider.py`](../src/tradescan/data/provider.py)):

```python
def history(self, tickers: Sequence[str], period: str, interval: str) -> dict[str, pd.DataFrame]: ...
```

It returns one normalized frame per ticker. Tickers without data are **omitted**, not raised, so one bad ticker
never fails a watchlist; use cases report them as `missing`.

**Frame shape.** `data/schema.normalize_ohlcv` guarantees: lowercase float columns `open, high, low, close,
volume`; a sorted, timezone-naive, duplicate-free `DatetimeIndex` named `date`; rows without prices dropped;
missing volume as `0` (indices and some FX or crypto feeds have none, so they never pass the `volume` filter).
Every component relies on this shape.

**Default source.** `YFinanceProvider` downloads all requested tickers in one batched `yfinance.download`
call with `auto_adjust=True` (prices adjusted for splits and dividends), then splits the result per ticker.
yfinance uses an unofficial Yahoo API: expect rate limits and format changes. The downloader is injectable
for tests.

**Cache.** `CachedProvider` decorates any provider. Layout:

```
<data.cache_dir>/<interval>/<period>/<TICKER>.parquet      (default .cache/1d/10y/SPY.parquet)
```

- A file is fresh while its modification time is younger than `data.cache_ttl_hours` (default 12 h).
- Only stale or missing tickers are fetched, in one batch; fresh ones come from disk.
- Writes go to a `.tmp` file that is then renamed, so a crash never leaves a half-written Parquet file.
- An unreadable file is ignored with a warning and re-fetched.
- Ticker names are sanitized for the file name (`[^A-Za-z0-9._-]` becomes `_`).
- `--no-cache` on a CLI command (and `serve`) skips the cache for that run. `.cache/` is git-ignored.

Data is cached per ticker, period and interval, so universes that overlap (`sp500`, `nasdaq100`) share files.
During market hours the last daily bar is still forming; run scans after the close.

## Watchlists

Text files in `config/watchlists/` (`<name>.txt`). Tickers are separated by whitespace, commas or semicolons;
`#` starts a comment. A comment line `# benchmark: SPY` sets the list's benchmark (used for relative strength,
market regime and the `market` filter). Tickers are upper-cased and de-duplicated, order is kept.

```
# Tech giants
# benchmark: QQQ
AAPL MSFT, NVDA   # comment
```

`load_watchlist` accepts a file path or a name; the API accepts **names only**. Bundled lists: `sp500` (benchmark
SPY), `nasdaq100` (QQQ), `us_large`, `wig20`, `etf`, `crypto`. The WIG20 index has no Yahoo history, so `wig20`
uses an ETF as its benchmark. `tradescan update-universes [--only sp500]` regenerates the two index lists from
Wikipedia's constituent tables; each file records the source and date, share classes are converted to Yahoo's
format (`BRK.B` becomes `BRK-B`), and the existing file is kept if the download or the sanity floor
(`min_members`) fails.

## Settings (`config/settings.toml`)

Loaded by `config.load_settings` into the frozen `Settings`. Rules:

- Every section and key is optional; missing ones fall back to the defaults declared in `config.py`.
- Unknown sections and unknown keys raise a `ValueError` (typos do not pass silently).
- A missing file yields the defaults. The CLI looks for `config/settings.toml` relative to the current
  directory, so run commands from the project folder or pass `--config`.
- Values outside a parameter's declared range are rejected at load time.
- A single run can override any declared parameter without touching the file (see
  [architecture.md](architecture.md#the-declared-parameter-system)).

| Section | Keys (defaults) | Used by |
| --- | --- | --- |
| `[data]` | `period` "5y", `interval` "1d", `cache_dir` ".cache", `cache_ttl_hours` 12 | scan, market (not overridable: paths and names are not parameters) |
| `[account]` | `equity` 100000, `risk_pct` 1.0, `max_position_pct` 25.0, `lot_size` 1 | scan risk plan, all backtests |
| `[risk]` | `atr_period` 14, `atr_mult` 2.0, `targets_r` [2.0, 3.0] | risk plan, initial stop |
| `[scan]` | `fresh_bars` 3, `min_score` 1.0, `benchmark` "SPY", `edge_horizon` 10, `min_bars` 60 | scanner; the `score` portfolio priority |
| `[scoring]` | `trend_bonus`, `weekly_bonus`, `rs_bonus` 1.0, `rs_strong_pct` 80, `[scoring.family_weights]`, `[scoring.signal_weights]` | confluence score |
| `[trend]` | `fast_period` 50, `slow_period` 200, `weekly_period` 30, `rs_periods`, `rs_weights` | trend and relative strength |
| `[regime]` | `fast_period` 50, `slow_period` 200, `high_low_period` 252, `risk_on_breadth` 60, `risk_off_breadth` 40 | market regime |
| `[backtest]` | `period` "10y", `commission_pct` 0.1, `slippage_pct` 0.05, `bars_per_year` 252, `oos_pct` 30 | all backtests |
| `[pyramid]` | `max_units` 1 (off), `add_every_atr` 0.5 | single-ticker backtest, sweep, walk-forward, watchlist backtest |
| `[monte_carlo]` | `simulations` 1000, `ruin_drawdown_pct` 50, `seed` 0 | backtest Monte Carlo |
| `[portfolio]` | `max_positions` 10, `max_exposure_pct` 100 | portfolio backtest |
| `[rotation]` | `holdings` 5, `absolute_lookback` 252 | rotation |
| `[walk_forward]` | `windows` 5, `in_sample_ratio` 3.0, `min_trades` 10 | walk-forward |

Cross-field checks are enforced in `__post_init__` (for example `trend.fast_period` must be below
`slow_period`, `regime.risk_off_breadth` must not exceed `risk_on_breadth`, `rs_periods` and `rs_weights` must
have the same length). Percent values are written as percents (`1.0` means 1%). Use `lot_size = 0.0001` for
crypto and `bars_per_year = 365` for 24/7 markets.

## SQLite database

`tradescan serve` keeps what must survive restarts in one SQLite file: `tradescan.db` in the folder `serve`
starts from (`--db PATH` picks another; git-ignored). The parent directory is created on first use.

Implementation notes ([`storage/database.py`](../src/tradescan/storage/database.py)):

- **A connection per operation**, opened by `Database.connect()` and committed or rolled back when the block
  ends, so the API's worker threads never share a connection.
- **Schema version = SQLite `PRAGMA user_version`.** `_MIGRATIONS` is a tuple of SQL scripts; opening the file
  runs the ones not applied yet, each in a transaction together with the version bump.
- **Append-only migrations.** Never edit an existing migration: files written by older versions are upgraded
  from it. A schema change is a *new* entry at the end.
- A file whose version is newer than the code, or that is not a tradescan database, is refused with a
  `ValueError`; `serve` migrates at startup so such a file stops the server before it listens.
- `Database.in_memory()` is a shared in-memory database kept alive by a keeper connection; `create_app` uses it
  when no database is given (state lasts only as long as the app), and tests use it.
- Stored JSON is limited to 2,000,000 bytes (`MAX_JSON_BYTES`); a ten-year daily equity curve is about 60 kB.

### Schema (migration 1)

```sql
CREATE TABLE pinned_runs (
    id TEXT PRIMARY KEY,
    slot INTEGER NOT NULL UNIQUE,     -- 1..8: number and colour in Compare
    name TEXT NOT NULL,
    hidden INTEGER NOT NULL,
    pinned_at TEXT NOT NULL,
    format INTEGER NOT NULL,          -- the UI's runs-file version of the snapshot
    snapshot TEXT NOT NULL            -- JSON, opaque to the server
);
CREATE TABLE journal_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL, direction TEXT NOT NULL,
    opened TEXT NOT NULL, entry_price REAL NOT NULL, quantity REAL NOT NULL,
    stop REAL,
    closed TEXT, exit_price REAL,
    fees REAL NOT NULL, notes TEXT NOT NULL,
    run_format INTEGER, run_snapshot TEXT,   -- the run that suggested the trade, copied
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
```

**Pinned runs** (`PinnedRunStore`): at most 8 (`MAX_PINNED_RUNS`, matching the UI's `MAX_RUNS`); `add` raises
`ConflictError` for a duplicate id or a taken slot. The server never interprets a snapshot; the UI versions it
(`format`) and upgrades older ones when it reads them.

**Journal** (`TradeJournal`): `trades()` returns newest opened first; `add`, `replace` (all fields) and `remove`.
A trade is open until it has an exit date and price. The profit is in the ticker's currency, so summaries add
up R multiples and percentages only, never money. A trade stores a copy of its suggesting run, so unpinning the
run leaves the trade intact.

### Backup and moving data

Copy `tradescan.db` while the server is stopped. **Export JSON** on the Compare page saves the pinned runs
alone and **Import JSON** restores them. Runs pinned by early versions, which lived in the browser's
`localStorage` under the key `tradescan.runs`, move to the server the first time the UI opens in that browser.

## Exports

`--export PATH` on the CLI commands that produce tables (`scan`, `edge`, `sweep`, `walk-forward`, the watchlist,
portfolio and rotation backtests and `rotation-sweep`) writes result tables with `report/export.py`: the extension picks the writer
(`.csv` or `.json`; anything else is an error). Parent directories are created. `exports/` is git-ignored.
To add a format, add a writer to `_WRITERS`.
