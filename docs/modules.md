# Module map

Every module under `src/tradescan`, grouped by layer, with its responsibility. Paths are relative to
`src/tradescan`. See [architecture.md](architecture.md) for how the layers connect.

## Core domain (top level)

| Module | Responsibility |
| --- | --- |
| `params.py` | Declared, range-checked parameters: `param(...)`, `ParamSpec`, `parameters_of`, `with_overrides`, `check_group`. |
| `config.py` | Frozen settings dataclasses (one per `settings.toml` section), TOML loading, `Settings.with_overrides`, `adjustable_sections`. |
| `indicators.py` | Vectorized, causal technical indicators (SMA, ATR, ADX, RSI, ...). |
| `context.py` | `TickerContext` (price, ATR, ADX, trends, raw relative strength) from `ContextBuilder`; also per-bar trend and RS arrays. |
| `scoring.py` | `Scorer`: confluence score = weighted fresh signals + daily/weekly trend and relative-strength bonuses. |
| `scanner.py` | `Scanner`: frames → ranked, risk-planned `ScanHit`s with the edge of the latest signal. |
| `regime.py` | `MarketRegimeAnalyzer`: risk-on / neutral / risk-off from benchmark trend and watchlist breadth. |
| `risk.py` | `trade_levels`, `position_size`, `RiskPlanner`: used by the scanner **and** both engines so all agree. |
| `journal.py` | Trade journal domain: `TradeEntry`, `JournalTrade`, `SuggestedBy`, per-trade and summary figures. |
| `watchlist.py` | Parse watchlist files (`#` comments, `# benchmark: X` directive), load by name. |
| `universes.py` | Refresh the `sp500` and `nasdaq100` watchlists from Wikipedia tables with sanity checks. |
| `parallel.py` | `TaskRunner` protocol; `SequentialRunner`, `ProcessRunner` (one worker per core, inline below 40 items). |

## `signals/`

| Module | Responsibility |
| --- | --- |
| `base.py` | `Signal` ABC, `Direction`, `Family`; `events()` keeps the first bar of each run. |
| `registry.py` | `SignalRegistry`, `default_registry`, the `@register` decorator, `select` by name/family/direction. |
| `conditions.py` | Boolean building blocks (`rising_edge`, `bars_since_last`, ...). |
| `trend.py`, `momentum.py`, `breakout.py`, `mean_reversion.py`, `volume.py`, `pattern.py` | The 38 built-in signals, one family per module. |

## `data/`

| Module | Responsibility |
| --- | --- |
| `provider.py` | `DataProvider` protocol: `history(tickers, period, interval)`; missing tickers are omitted, not raised. |
| `yfinance_provider.py` | Batched Yahoo download (split/dividend-adjusted), splits the result per ticker. |
| `cache.py` | `CachedProvider`: Parquet per ticker/period/interval, TTL by file mtime, atomic writes, one batch for stale tickers. |
| `schema.py` | `normalize_ohlcv`: lowercase float OHLCV, sorted tz-naive unique index; `bar_dates`, `bar_position`. |

## `backtest/`

| Module | Responsibility |
| --- | --- |
| `base.py` | `BacktestConfig`, `Trade`, `Fill`, `BacktestResult`, `ExitReason`, the `BacktestEngine` protocol. Documents the shared execution rules. |
| `rules.py` | `Bars` (numpy arrays), `Rule` base, generic `RuleRegistry`. |
| `entries.py` | Entry rules: `next_open`, `stop`, `limit`; `OrderType`, `EntryOrders`. |
| `filters.py` | Entry filters: `trend`, `market`, `adx`, `volume`, `atr_pct`. |
| `exits.py` | Exit rules and trackers: `target`, `time`, `trailing`, `channel`, `breakeven`, `rsi`, `sma_revert`, `sma_trend`, `supertrend`, `failed_breakout`, `no_progress`; `CombinedExits` takes the tightest stop. |
| `trade_rules.py` | `TradeRules`, `PreparedRules`, `EntryPlan`, `RuleChoice`, `RuleCatalog`, `default_catalog`. |
| `pyramid.py` | Turtle-style adds: `Pyramiding`, `Units`. |
| `vectorized.py` | `VectorizedEngine` and `FillModel`. |
| `cerebro.py` | `CerebroEngine` and `MultiFeedBroker` (optional dependency). |
| `metrics.py` | `compute_metrics`: return, CAGR, Sharpe, Sortino, drawdown, win rate, profit factor, expectancy R, SQN, exposure, buy & hold. |
| `oos.py` | `Split`, `split_history`, `run_periods`, `MIN_PERIOD_BARS`. |
| `monte_carlo.py` | `simulate` (shuffled and bootstrapped), `MonteCarloConfig`. |
| `edge.py` | Forward returns after each past signal event, compared with the average bar. |
| `sweep.py` | `SweepAxis`, `SweepTarget`, grid limits, `SweepCase`. |
| `walk_forward.py` | Windows, selection metrics, stitching of out-of-sample windows. |
| `tickers.py` | `TickerJob`/`TickerRun`: one setup on one ticker, the unit of work a `TaskRunner` maps. |
| `pooled.py` | Pooled R statistics and metric spread across tickers. |
| `allocation.py` | `PortfolioConfig`, `Candidate`, `Allocation`: which signals get orders at one close, and their size. |
| `priority.py` | Priority rules: `relative_strength`, `momentum`, `score` (the last reads the scanner). |
| `portfolio.py` | `PortfolioEngine` protocol and `VectorizedPortfolioEngine`. |
| `cerebro_portfolio.py` | Cerebro reference for the portfolio. |
| `portfolio_metrics.py` | Portfolio-specific stats (open positions, exposure, skipped signals). |
| `weighting.py` | Weight rules for rotation: `equal`, `inverse_volatility`. |
| `rotation.py` | Rotation engine, `Rebalance`, `RotationConfig`, ranking defaults. |
| `cerebro_rotation.py` | Cerebro reference for the rotation. |
| `rotation_metrics.py` | Rotation stats (holdings, defensive share, turnover, costs). |
| `rotation_sweep.py` | Grid over rotation parameters, in-sample and out-of-sample. |

## `services/` (use cases)

One module per workflow. Each takes its collaborators in the constructor and exposes a `run`-style method that
takes a frozen request dataclass.

| Module | Use case |
| --- | --- |
| `composition.py` | `build_use_cases`, `UseCases`, default engines/provider factories. |
| `builders.py` | Settings → `Scorer`, `ContextBuilder`, `MarketRegimeAnalyzer`, `RiskPlanner`, configs; `resolve_settings`. |
| `market_data.py` | `MarketData` loader, `SignalFilter`, `benchmark_ticker`. |
| `scan.py`, `market.py`, `edge.py`, `chart.py` | Scanner, regime, signal edge, chart data. |
| `backtest.py` | `BacktestUseCase`, `BacktestRequest`, `resolve_backtest`, `load_setup`. |
| `sweep.py`, `walk_forward.py` | `SweepGridBuilder` and the two use cases; `SWEEP_SECTIONS`, `NOT_SWEEPABLE`, `NOT_WALKABLE`. |
| `watchlist_backtest.py` | One setup on every ticker. |
| `portfolio.py` | Shared-equity portfolio. |
| `rotation.py`, `rotation_sweep.py` | Momentum rotation and its sweep. |

## `api/`

| Path | Responsibility |
| --- | --- |
| `app.py` | `create_app`: middleware, exception handlers, `ROUTERS`, static UI mount (`SpaStaticFiles`). |
| `context.py` | `ApiContext`: settings, use cases, registry, stores; resolves universes (names only) and signal filters. |
| `routes/*.py` | One router per endpoint group, each with `build_router(context)`. |
| `schemas/*.py` | pydantic request/response models. Requests derive from `RequestModel` (`extra="forbid"`). |
| `mappers/*.py` | Domain result → response model; `common.py` has `finite`, `day`, `points`. |

## `cli/`

| Path | Responsibility |
| --- | --- |
| `__init__.py` | `build_parser`, `main`; maps `FileNotFoundError`, `KeyError`, `ValueError`, `ImportError` to exit code 2. |
| `command.py` | `Command` dataclass (name, help, add_arguments, run). |
| `commands/*.py` | One module per subcommand exposing `COMMAND`; listed in `commands/__init__.py:COMMANDS`. |
| `arguments.py`, `inputs.py`, `output.py` | Shared argument groups, argument → use-case input translation, shared output helpers. |
| `wiring.py` | Provider and use-case construction for commands (uses `ProcessRunner`). |

## `storage/` and `report/`

| Module | Responsibility |
| --- | --- |
| `storage/database.py` | `Database` (connection per operation, `user_version` migrations), `NotFoundError`, `ConflictError`, `encode_json`. |
| `storage/runs.py` | `PinnedRunStore`; at most `MAX_PINNED_RUNS = 8`, unique slot. |
| `storage/trades.py` | `TradeJournal` CRUD over `journal_trades`. |
| `report/console.py` | Rich terminal rendering (`ConsoleReport`). |
| `report/tables.py` | Domain results → DataFrames shared by terminal and file export. |
| `report/export.py` | `export_frame` to `.csv` or `.json` by extension. |

## Outside the package

| Path | Purpose |
| --- | --- |
| `config/settings.toml` | Defaults of the settings sections. |
| `config/watchlists/*.txt` | Bundled watchlists: `sp500`, `nasdaq100`, `us_large`, `wig20`, `etf`, `crypto`. |
| `scripts/export_openapi.py` | Writes the OpenAPI schema for the frontend's type generation. |
| `tests/` | Python tests on deterministic synthetic data (`tests/synthetic.py`). |
| `frontend/` | React app; see [frontend.md](frontend.md). |
| `ROADMAP.md` | Item list and status. |
| `docs/INSTRUKCJA.md` | Polish end-user manual. |
