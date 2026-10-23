# Development guide

How to set up, run, test, extend and contribute to tradescan.

## Requirements

- Python 3.11 or newer (the project is tested with 3.13, pandas 3 and numpy 2)
- Node.js and npm for the frontend
- Optional extras: `cerebro` (backtrader), `api` (FastAPI, uvicorn), `dev` (pytest, httpx2, ruff, mypy,
  pandas-stubs)

Runtime dependencies: `lxml`, `numpy`, `pandas`, `pyarrow`, `rich`, `yfinance`.

## Setup

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[cerebro,api,dev]"      # Windows
npm --prefix frontend install
npm --prefix frontend run build
```

`pip install -e` registers the `tradescan` console script (`tradescan.cli:main`; `python -m tradescan.cli`
also works). Run commands from the project folder so `config/settings.toml` and `config/watchlists/` are found,
or pass `--config` and `--watchlists-dir`.

## Running

```bash
tradescan list-signals
tradescan scan -w sp500 --min-score 4
tradescan backtest SPY donchian_breakout --engine both
tradescan serve                          # UI + API on http://127.0.0.1:8000
```

Every command and flag is documented in the README's "Usage" section. For UI work run `tradescan serve` and
`npm --prefix frontend run dev` side by side (see [frontend.md](frontend.md)). `.claude/launch.json` defines a
preview configuration for the server on port 8765 (the `.claude/` folder is git-ignored).

## Testing and quality

```bash
.venv\Scripts\python -m pytest                      # Python tests, no network
npm --prefix frontend test                          # Vitest
npm --prefix frontend run typecheck

.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .       # `ruff format .` rewrites
.venv\Scripts\python -m mypy                        # strict, over src, tests, scripts
npm --prefix frontend run lint
npm --prefix frontend run format:check              # `npm run format` rewrites
```

Configuration lives in `pyproject.toml`: Ruff (line length 120, rules E, W, F, I, N, B, UP, SIM, C4, PIE, RET,
PERF, PT, RUF; `×` allowed because labels print "2 × ATR"), mypy `strict = true` with the pydantic plugin
(tests are checked without requiring annotations on every test function; `backtrader` and `yfinance` have no
type information; the Cerebro modules may subclass untyped backtrader classes). `.editorconfig` sets editor
defaults. The repository has no CI workflow file; run the checks above before opening a pull request.

### How the Python tests work

- They run on **deterministic synthetic data** (`tests/synthetic.py`: a seeded random walk with volatility
  regimes, gaps and volume, plus a `FixedSignal` that fires on chosen bars) and fake providers. They never touch the
  network.
- API tests build the real app with `create_app` and an in-memory `Database`.
- Engine parity: tests run every rule on both engines and require identical trades. A new rule is covered by
  this automatically once it is registered.
- Look-ahead guard: a test checks that adding future bars never changes past signals.
- Parameter guard: a test fails if a signal's `description` does not use each declared parameter.

| Test module | Covers |
| --- | --- |
| `test_signals`, `test_indicators` | Signal conditions and causality; indicators |
| `test_scanner_regime_edge`, `test_risk_scoring` | Scanner, regime, edge, scoring, risk |
| `test_backtest`, `test_entry_filters`, `test_exit_rules`, `test_pyramid` | Single-ticker engines and rules, parity |
| `test_oos_sweep`, `test_walk_forward`, `test_monte_carlo` | Splits, sweeps, walk-forward, Monte Carlo |
| `test_watchlist_backtest`, `test_portfolio`, `test_rotation`, `test_rotation_sweep` | Multi-ticker engines |
| `test_params`, `test_config_watchlist`, `test_universes` | Parameter system, settings, watchlists, index lists |
| `test_data`, `test_parallel` | Provider, cache, task runners |
| `test_storage`, `test_journal`, `test_api`, `test_cli` | Persistence, journal, HTTP API, command line |

## Extension checklist

Each extension point is a new class or module that is registered, not an edit to existing logic.

| To add | Do | Where it shows up |
| --- | --- | --- |
| **Signal** | Subclass `Signal`, implement `condition`, decorate with `@register`, import the module in `signals/__init__.py`. Declare every number with `param(...)` and use it in `description` (a test enforces this). Keep it causal. | Scanner, scoring, edge, both engines, CLI, API, UI |
| **Entry filter / entry rule / exit rule** | Subclass `EntryFilter` (`backtest/filters.py`), `EntryRule` (`backtest/entries.py`) or `ExitRule` (`backtest/exits.py`); register with `@entry_filters.register`, `@entry_rules.register` or `@exit_rules.register`; declare numbers with `param(...)`. | Both engines, API (`/api/config`), CLI, UI; parity test |
| **Ranking / weighting rule** (rotation) | `TickerPriorityRule` (`backtest/priority.py`) or `WeightRule` (`backtest/weighting.py`) with `@priority_rules.register` / `@weight_rules.register`. | Rotation and portfolio |
| **Data source** | Implement `DataProvider.history`; wrap with `CachedProvider`. | Pass to `build_use_cases` / `create_app` |
| **Backtest engine** | Implement `BacktestEngine.run`; add it to `default_engines()` in `services/composition.py` (and the portfolio/rotation factories if applicable). | CLI `--engine`, API, UI engine picker |
| **Use case** | New module in `services/` taking collaborators in its constructor; add it to `UseCases` and `build_use_cases`. | Then add a route and/or command |
| **API endpoint** | Router module in `api/routes/` with `build_router(context)`; list it in `ROUTERS` in `api/app.py`; add schemas and mapper; regenerate the frontend types. | `/docs`, UI |
| **CLI command** | Module in `cli/commands/` with `COMMAND = Command(...)`; list in `COMMANDS` in `cli/commands/__init__.py`. | `tradescan --help` |
| **Stored data** | A store next to `PinnedRunStore` / `TradeJournal` in `storage/` using the shared `Database`; append a new migration to `_MIGRATIONS` (never edit an old one). | Database file |
| **Export format** | Add a writer to `_WRITERS` in `report/export.py`. | `--export` |
| **Settings section** | Frozen dataclass in `config.py` with `param(...)` fields, a field on `Settings`; add the defaults to `config/settings.toml`. | Config API, UI advanced settings |

Worked example of a signal:

```python
@register
@dataclass(frozen=True)
class InsideDayBreakout(Signal):
    buffer_pct: float = param(0.0, minimum=0.0, maximum=5.0, step=0.1, label="Breakout buffer", unit="%")
    name = "inside_day_breakout"
    family = Family.BREAKOUT
    direction = Direction.LONG
    description = "Close at least {buffer_pct:g}% above the high of an inside day"

    def condition(self, df: pd.DataFrame) -> pd.Series:
        inside = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))
        level = df["high"].shift(1) * (1 + self.buffer_pct / 100)
        return inside.shift(1, fill_value=False) & (df["close"] > level)
```

## Code conventions

- **SOLID, pragmatically.** One responsibility per module; new behaviour as a new implementation; small
  protocols (`DataProvider`, `TaskRunner`); dependencies injected through constructors. Do not add an interface
  for a single implementation unless it is a test seam or a module boundary.
- **No logic in `cli/` or `api/`.** They translate input and output only.
- **Frozen dataclasses** for values and configuration; collections inside are immutable (tuples).
- **Declare, don't hard-code.** A number that changes a result is a `param(...)`, so it reaches the API, UI, URL,
  pinned runs and sweeps.
- **Causal indicators.** Nothing may read a future bar; the guard test depends on it.
- **Comments** explain why, not what. English for code, identifiers and comments.
- **Error handling:** raise `ValueError` for bad input (the API turns it into 400 and the CLI into exit code 2),
  `NotFoundError` / `ConflictError` from storage.
- **Windows:** the Parquet cache and SQLite paths work on Windows; `ProcessRunner` starts worker processes, which
  costs a few seconds, so it runs inline for inputs under 40 items. Functions given to it must be picklable
  (module level).

## Working with the roadmap and git

`ROADMAP.md` lists the items (F foundation, C comparing, O optimization, B breakout, M mean-reversion, T trend,
R rotation strategies). An item gets a GitHub issue when work on it starts and its pull request updates the
row. The history shows the convention: one issue per change, a branch named `<type>/<issue>-<short-description>`
(`feat`, `fix`, `refactor`, `docs`, `chore`), one pull request per branch, merged after review. Before opening a
pull request, run the quality checks above; the description should say what changed and why, how it was
verified, and `Closes #<issue>`.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `The cerebro engine needs backtrader` (HTTP 501 from the API) | Install the extra: `pip install -e .[cerebro]`. |
| `The web server needs the api extra` | `pip install -e .[api]`. |
| `serve` runs but shows only JSON | `frontend/dist` is missing: `npm --prefix frontend run build`, or pass `--static`. |
| `Watchlist 'x' not found` | Run from the project folder or pass `--watchlists-dir`. |
| `... is not a tradescan database` / `written by a newer tradescan` | The `--db` file is not ours or comes from a newer version; point `--db` elsewhere. |
| API answers 400 on every request from another machine or name | The `Host` header is not local; see the security notes in [api.md](api.md). |
| Missing tickers in results | Yahoo returned nothing for them; run with `-v` to see download warnings, or `--no-cache` to force a fresh download. |
| Sweep marks cells as failed | The combination breaks a rule between parameters (for example a fast average not shorter than the slow one); the other cells are valid. |
| Stale data | The cache is fresh for `data.cache_ttl_hours` (12 h); use `--no-cache` or delete `.cache/`. |
