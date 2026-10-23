# Architecture

tradescan is a Python package (`src/tradescan`) with a React single-page app (`frontend/`) on top. This
document explains how the pieces fit together and why. For what each file does see [modules.md](modules.md);
for the trading rules the engines implement see the "How it works" section of the [README](../README.md).

## Layers

```
 CLI (cli/)                 HTTP API (api/)  ──serves──  React UI (frontend/)
      │  translate input/output  │
      └───────────┬──────────────┘
                  ▼
        Use cases (services/)        one module per workflow; built by services/composition.py
                  │
   ┌──────────────┼───────────────────────────────┐
   ▼              ▼                               ▼
 Domain        Backtest engines               Data access
 signals/      backtest/ (rules, engines,     data/ (provider, Parquet cache)
 scanner.py    metrics, oos, sweep, ...)      watchlist.py, universes.py
 scoring.py    risk.py, params.py             storage/ (SQLite: pinned runs, journal)
 regime.py     config.py
```

Dependencies point downwards only. `cli/` and `api/` hold no business logic: they parse input, call a use case
in `services/`, and render the result (Rich tables, or pydantic models through the `api/mappers`). A use case
never imports `cli` or `api`. This keeps the same workflow reachable from the terminal, the HTTP API and tests.

## Composition and dependency injection

Everything is wired in one place, `build_use_cases` in
[`services/composition.py`](../src/tradescan/services/composition.py), which returns a frozen `UseCases` bundle
(scan, market, edge, backtest, sweep, walk_forward, watchlist_backtest, portfolio, rotation, rotation_sweep, chart).
Collaborators are passed in, never created inside the logic:

| Collaborator | Abstraction | Default |
| --- | --- | --- |
| Market data | `DataProvider` protocol (`data/provider.py`) | `YFinanceProvider` wrapped in `CachedProvider` |
| Signals | `SignalRegistry` | `default_registry`, filled by importing `tradescan.signals` |
| Trade rules | `RuleCatalog` (entries, exits, filters) | `default_catalog` |
| Backtest engines | name → factory mappings | `vectorized`, `cerebro` (loaded lazily) |
| Per-ticker parallelism | `TaskRunner` protocol (`parallel.py`) | `SequentialRunner`; `ProcessRunner` for the CLI and server |
| Settings | frozen `Settings` dataclass | `config/settings.toml` merged over built-in defaults |

The CLI builds the bundle in `cli/wiring.py`. The API builds it in `create_app` (`api/app.py`), which also
creates the `PinnedRunStore` and `TradeJournal` on a shared `Database`. Tests pass fakes (a fake provider, an
in-memory database), which is why the Python suite never touches the network.

## The declared-parameter system

The most important cross-cutting idea. A number that changes a result is **declared once**, on the dataclass
field that holds it:

```python
period: int = param(20, minimum=2, maximum=500, step=1, label="Channel period", unit="bars")
```

[`params.py`](../src/tradescan/params.py) turns these declarations into `ParamSpec` objects
(`parameters_of(cls)`), validates and applies per-run overrides (`with_overrides`, `check_group`), and keeps
defaults, ranges and labels together. Signals, entry filters, entry rules, exit rules, priority rules, weight
rules and every settings section (`config.py`) all use it. Consequences:

- **API:** `GET /api/config` and `GET /api/signals` publish the specs; request bodies carry overrides
  (`"settings": {"risk": {"atr_mult": 3}}`, `"params": {...}`) that are validated against the same ranges.
- **UI:** forms are generated from the specs, so a new parameter appears with no frontend work
  (see [frontend.md](frontend.md)).
- **CLI:** flags map onto the same overrides in `cli/inputs.py`.
- **Sweeps and walk-forward:** any single-number parameter can be an axis.
- **Tests:** a test fails if a signal's description does not use every declared parameter.

Values outside the range, unknown names, and anything that is not a declared parameter (paths, cache settings)
are refused with a `ValueError`, which the API maps to HTTP 400.

## Settings flow

`load_settings` reads `config/settings.toml` (every key optional, unknown keys rejected) into the frozen
`Settings`. A single run never mutates it: `Settings.with_overrides` returns a new instance with validated
overrides. `services/builders.py` then turns settings into the collaborators a use case needs (`Scorer`,
`ContextBuilder`, `MarketRegimeAnalyzer`, `RiskPlanner`, `BacktestConfig`, `MonteCarloConfig`, `PortfolioConfig`,
`RotationConfig`).

## Signals and the scanner

A `Signal` (`signals/base.py`) is a frozen dataclass with `name`, `family`, `direction`, a `description`
template and a causal boolean `condition(df)`. `events()` keeps only the first bar of each run (a rising
edge), so a signal can be counted, scored and backtested identically. There are 38 signals in six families
(trend, momentum, breakout, mean reversion, volume, pattern). `@register` adds a class to `default_registry`;
importing `tradescan.signals` imports every family module.

The scan path (`services/scan.py` → `scanner.py`): load frames → build a `TickerContext` per ticker (price, ATR,
ADX, daily and weekly trend, raw relative strength) → evaluate signals → keep those fresh within
`scan.fresh_bars` → score (`scoring.py`: weighted fresh signals plus trend, weekly and relative-strength
bonuses) → attach a `RiskPlan` (`risk.py`) and the historical edge of the most recent signal on that ticker.
`ContextBuilder` also exposes the same facts at every bar (`daily_trends`, `weekly_trends`,
`relative_strengths`) so the portfolio's `score` priority can score like the scanner without look-ahead.

## Backtest design

### Rules, not engine code

A backtest is a signal plus **trade rules** (`backtest/trade_rules.py`): entry filters, one entry rule, and
exit rules on top of an always-on initial ATR stop. Rules are frozen dataclasses registered in a
`RuleRegistry` (`@entry_filters.register`, `@entry_rules.register`, `@exit_rules.register`). They work on numpy
arrays (`Bars`) and compute their levels **once per run**; the engines only execute the orders the rules ask
for. `TradeRules.prepare` produces `PreparedRules`, which both engines query with the same two questions:
`plan` (which order does a signal at bar *t* place, if the filters allow it) and `track` (which exit orders
does an open trade have). Because of this a new rule never needs an engine change.

`RuleCatalog.build` validates a request's `RuleChoice` objects (name + parameter overrides) into a `TradeRules`.
No exits given means the defaults (`target`, `time`); an empty list keeps only the stop.

### Two engines, one behaviour

| Engine | Module | Purpose |
| --- | --- | --- |
| `vectorized` | `backtest/vectorized.py` | Default. numpy; signals, levels and daily P&L are vectorized, only order fills loop over a trade's bars. Used by sweeps, walk-forward, watchlist and (by default) portfolio/rotation. |
| `cerebro` | `backtest/cerebro*.py` | Reference. backtrader's event loop with real market/stop/limit orders, OCO stop and target, percentage commission and slippage. Optional (`.[cerebro]`), loaded lazily by `composition.py`. |

Both read the same precomputed levels, follow the same fill semantics (the vectorized `FillModel` copies
backtrader's percentage slippage: the stop wins over the target on a bar that touches both, a gap fills at the
open, slippage never leaves the bar's range), and are required to
produce **identical trades**; the engine-parity tests run every rule on both. The same pattern repeats for the
portfolio (`portfolio.py` / `cerebro_portfolio.py`) and rotation (`rotation.py` / `cerebro_rotation.py`) engines.
New engines are added to the factory maps in `composition.py` and appear in the CLI, API and UI automatically.

Cerebro's broker is configured so cash never limits a fill (`LEVERAGE = 1e9`), matching the vectorized engine;
`MultiFeedBroker` makes an order only fill on a bar of its own feed after the bar it was placed on.

### Periods, sweeps, walk-forward, Monte Carlo

- **In-sample / out-of-sample** (`backtest/oos.py`): the history is split once, at `backtest.oos_pct` (default
  30%) from the end. The in-sample run only receives bars before the split. The out-of-sample run receives the
  full history (so indicators are warm) but its signal fires only from the split on, with fresh equity. Each
  period needs at least `MIN_PERIOD_BARS = 60`; otherwise the split is omitted. Every engine reports periods
  through `run_periods`, so all are consistent.
- **Sweep** (`backtest/sweep.py`, `services/sweep.py`): one or two axes, at most 200 combinations (2–50 values
  per axis), each run on both periods with the vectorized engine through a `TaskRunner`. A combination that
  violates a rule between parameters is reported as failed; the rest still run.
- **Walk-forward** (`backtest/walk_forward.py`): `windows` out-of-sample windows of equal length, each preceded
  by an in-sample window `in_sample_ratio` times as long (`rolling` or `anchored`). Every window picks the combination with the
  highest selection metric among those with enough trades; picks trade their out-of-sample window and the
  windows are stitched into one equity curve. At most `MAX_RUNS = 2000` backtests.
- **Monte Carlo** (`backtest/monte_carlo.py`): closed trades in R are resampled (shuffled, bootstrapped) and
  traded with fixed-fractional sizing to spread drawdown, losing streak and final return. Needs at least two
  closed trades.
- **Multi-ticker** (`backtest/tickers.py`, `pooled.py`): the watchlist backtest runs a `TickerJob` per ticker
  through the `TaskRunner`; `pooled.py` pools trades in R and computes the spread of a metric across tickers.
- **Portfolio** (`backtest/portfolio.py`, `allocation.py`, `priority.py`): one shared equity; at each close of the
  shared calendar `allocation.py` ranks fired signals by a priority rule and sizes them under `max_positions`
  and `max_exposure_pct`.
- **Rotation** (`backtest/rotation.py`, `weighting.py`): at the last day of each week or month, a ranking rule
  picks the top `holdings`; an absolute-momentum check can swap a slot to a safe asset or cash; a weight rule
  shares the equity; only the share difference trades at the next open.

## One request, end to end

`POST /api/backtest` with `{"ticker": "SPY", "signal": "donchian_breakout", "engines": ["vectorized", "cerebro"]}`:

1. `api/routes/backtest.py` validates the body (`BacktestIn`, `extra="forbid"`), checks the signal name, and
   builds a `BacktestRequest`.
2. `BacktestUseCase.run` resolves it (`resolve_backtest`): applies settings overrides, creates the signal with
   validated params, builds `TradeRules` from the catalog, builds `BacktestConfig`, and decides whether a
   benchmark is needed (only when a filter compares the market).
3. `MarketData.load` fetches the ticker (and benchmark) through the `CachedProvider`; the result is split into
   in-sample and out-of-sample.
4. For each requested engine: `engine.run`, `compute_metrics`, `run_periods`, and a Monte Carlo of the trades.
5. The report is mapped to `BacktestOut` by `api/mappers/backtest.py` (non-finite floats become `null`,
   dates become `YYYY-MM-DD`, series become `{time, value}` points).
6. Errors are mapped centrally in `create_app`: `ValueError` → 400, `NotFoundError` → 404, `ConflictError` →
   409, `ImportError` (Cerebro not installed) → 501.

## Persistence

SQLite via `storage/database.py`: one file (`tradescan.db`), a connection per operation (so worker threads
never share one), schema version in `PRAGMA user_version`, **append-only migrations**. Two stores sit on it:
`PinnedRunStore` (the UI's frozen run snapshots, at most 8) and `TradeJournal`. The server treats a snapshot as
opaque JSON owned by the UI. Details in [data-and-storage.md](data-and-storage.md).

## Security model

The API has no authentication and is meant for the local machine. `tradescan serve` binds to 127.0.0.1 and
warns when `--host` is not loopback. `TrustedHostMiddleware` accepts only `localhost`, `127.0.0.1`, `[::1]` and
the `--host` value, answering anything else with 400, which blocks DNS-rebinding from a web page. The API takes
watchlist **names** only, never file paths. Request models reject unknown fields.

## Frontend relationship

The UI is a static build served by the same FastAPI process (`SpaStaticFiles`, with an `index.html` fallback so
client-side routes survive a reload; `/api` is never rewritten). TypeScript types are generated from the API's
OpenAPI schema, so a change to an `api/schemas` model is a compile-time change in the UI. See
[frontend.md](frontend.md).

## Design rules the codebase follows

- Each extension point is a new class, not an edit to existing logic (open/closed). See the checklist in
  [development.md](development.md).
- Abstractions exist where there is a second implementation or a test seam (`DataProvider`, `TaskRunner`,
  `BacktestEngine`, rule registries), not on speculation.
- Frozen dataclasses everywhere; mypy runs in strict mode over `src`, `tests` and `scripts`.
- Indicators and signals are causal; a test checks that adding future bars never changes past signals.
