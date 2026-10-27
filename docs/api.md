# HTTP API reference

The API is a FastAPI app (`tradescan.api.app:create_app`) mounted under `/api`. Interactive docs are served by
FastAPI at `/docs` (Swagger UI) and `/openapi.json` while `tradescan serve` runs. This page is the map; the
exact field lists live in the pydantic models in `src/tradescan/api/schemas/` and in the generated OpenAPI.

Start it with `tradescan serve` (default `http://127.0.0.1:8000`). The built UI is served from the same process.

## Conventions

- **Bodies are JSON; analysis endpoints are `POST`** because their input is a structured setup. They only
  read data and compute, they do not change server state (only `/runs` and `/journal` do).
- **Unknown fields are rejected.** Request models derive from `RequestModel` (`extra="forbid"`), so a misspelt
  or removed field returns an error instead of being ignored.
- **Per-run overrides.** `settings` is `{section: {name: value}}` (for example `{"risk": {"atr_mult": 3}}`),
  `params` / `signal_params` hold signal parameters, rules take `{"name": ..., "params": {...}}`. All values are
  validated against the declared ranges published by `GET /api/config` and `GET /api/signals`.
- **Universe.** Endpoints that work on many tickers take exactly one of `watchlist` (a bundled watchlist
  **name**, never a path) or `tickers` (an ad-hoc list).
- **Numbers.** Non-finite floats are returned as `null`. Dates are `YYYY-MM-DD`. Series are lists of
  `{"time": "YYYY-MM-DD", "value": number}`.
- **Periods.** `period` is a yfinance period string (for example `5y`); omitted, the configured default is used.

### Errors

Errors always have the shape `{"detail": "<message>"}`.

| Status | Raised by | Meaning |
| --- | --- | --- |
| 400 | `ValueError`; `HTTPException` for unknown signals | Invalid input: value out of range, unknown name, rule conflict, no data for a ticker, unknown engine. |
| 404 | `NotFoundError`; unknown watchlist | No pinned run, journal trade or watchlist with that id/name. |
| 409 | `ConflictError` | A pinned run's id is already pinned or its slot is taken. |
| 422 | FastAPI validation | Body does not match the model (missing field, wrong type, unknown field). |
| 501 | `ImportError` | A requested engine needs an extra that is not installed (`cerebro` needs backtrader). |
| 400 | `TrustedHostMiddleware` | The `Host` header is not a local name (see Security). |

## Endpoints

### Meta and reference data

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/health` | `{"status": "ok", "version": ...}` |
| GET | `/api/config` | `ConfigOut`: every adjustable settings section with defaults and ranges, the entry/exit/filter/priority/ranking/weighting rules with their parameters, engine names, defaults, rebalance choices, and the limits of sweeps, rotation sweeps and walk-forward. The UI builds its forms from this. |
| GET | `/api/signals` | The 38 signals: name, family, direction, scoring weight, description, template and every parameter's spec. |
| GET | `/api/watchlists` | Bundled watchlists: name, tickers, benchmark. |

### Scanning

| Method | Path | Body | What it does |
| --- | --- | --- | --- |
| POST | `/api/scan` | `ScanIn`: universe, signal filter (`signals`, `families`, `direction`), `settings`, `signal_params`, `benchmark`, `period` | Fresh signals, scored and ranked, each with a risk plan and the edge of the latest signal. |
| POST | `/api/market` | `MarketIn`: universe, `settings`, `benchmark`, `period` | Market regime: risk-on / neutral / risk-off with benchmark trend, breadth, new highs and lows. (`/api/scan` also returns the regime, and the web UI reads it from there.) |
| POST | `/api/edge` | `EdgeIn`: universe, signal filter, `signal_params`, `horizons` (default 5, 10, 20), `min_events`, `period` | Win rate and return after each signal at each horizon, versus the average bar. |
| POST | `/api/chart` | `ChartIn`: `ticker`, `signals`, `signal_params`, `period` | Candles, moving averages and signal events for the chart. |

### Backtests

All of these accept the shared setup (`BacktestRulesIn`): `signal`, `params`, `settings`, `entry`, `exits`
(omit for the defaults, `[]` for only the initial stop), `filters`, `benchmark`, `period`.

| Method | Path | Extra body fields | What it does |
| --- | --- | --- | --- |
| POST | `/api/backtest` | `ticker`, `engines` (default `["vectorized"]`) | One signal on one ticker with one or both engines: metrics, equity, trades (with pyramiding adds), in-sample vs out-of-sample metrics, Monte Carlo. |
| POST | `/api/sweep` | `ticker`, `axes` (1–2) | The setup over a grid of one or two parameters; per-cell in-sample and out-of-sample metrics. |
| POST | `/api/walk-forward` | as sweep plus `scheme`, `metric` | Re-tuned on each in-sample window, traded on the next; stitched out-of-sample curve, efficiency, next setting. |
| POST | `/api/watchlist-backtest` | universe (no `ticker`) | The setup on every ticker: per-ticker metrics, pooled R statistics, spread of a metric. |
| POST | `/api/portfolio-backtest` | universe, `engines`, `priority`, `score_signal_params` | One shared equity with `max_positions` and `max_exposure_pct` limits (set through `settings.portfolio`); skipped signals, per-ticker contribution. Pyramiding above 1 unit is refused. |

A sweep `axis` is `{"target": "signal|entry|exit|filter|settings", "owner": ..., "name": ..., "values": [...]}`;
`owner` names the rule (for `exit` and `filter`) or the settings section (for `settings`). Limits: at most 2 axes,
2–50 values per axis, 200 combinations (walk-forward: 2000 backtests in total). Use `GET /api/config` for
the exact limits and the parameters that cannot be swept (`fixed`).

### Rotation

| Method | Path | Body | What it does |
| --- | --- | --- | --- |
| POST | `/api/rotation-backtest` | `RotationIn`: universe, `ranking`, `weighting`, `rebalance` (`weekly`/`monthly`), `safe_asset`, `settings` (`rotation`, `backtest`), `benchmark`, `period`, `engines` | Momentum rotation with one shared equity; holdings over time, what a rebalance at the last close would pick. |
| POST | `/api/rotation-sweep` | `RotationSweepIn`: the rotation setup (without engines) and `axes` with targets `ranking`, `weighting`, `settings` | Grid over rotation parameters, in-sample and out-of-sample. |

### Pinned runs (stateful)

Pinned runs are the UI's frozen snapshots for Compare. The server stores the `snapshot` object unchanged; the
UI owns its format and sends `format` (its runs-file version) next to it.

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/runs` | All runs, ordered by slot. |
| POST | `/api/runs` | Pin a run (`id`, `slot` 1–8, `name`, `hidden`, `pinned_at`, `format`, `snapshot`). 201 on success; 409 if the id is pinned or the slot is taken. |
| PATCH | `/api/runs/{run_id}` | Rename or hide/show (`name`, `hidden`). 404 if unknown. |
| DELETE | `/api/runs/{run_id}` | Unpin. 204; 404 if unknown. |
| DELETE | `/api/runs` | Unpin everything. 204. |

A snapshot is limited to 2,000,000 bytes of JSON (`MAX_JSON_BYTES`).

### Journal (stateful)

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/journal` | All trades (latest opened first) with per-trade profit, return and R, and a summary of open/closed counts, win rate, average return, average and total R. |
| POST | `/api/journal/trades` | Log a trade (`JournalTradeIn`: `ticker`, `direction`, `opened`, `entry_price`, `quantity`, optional `stop`, `closed`, `exit_price`, `fees`, `notes`, and `run`, the pinned run that suggested it). 201. |
| PUT | `/api/journal/trades/{trade_id}` | Replace a trade with all fields of the body. 404 if unknown. |
| DELETE | `/api/journal/trades/{trade_id}` | Delete. 204; 404 if unknown. |

A trade with `closed` (the exit date) and `exit_price` is closed. R is computed from the initial `stop`; without a stop
a trade has no R. A trade keeps its own copy of the suggesting run, so unpinning the run does not change it.

## Security

- No authentication. Do not expose the server to a network; the journal holds real trades.
- `serve` binds to `127.0.0.1` by default and prints a warning for any other `--host`.
- `TrustedHostMiddleware` allows `localhost`, `127.0.0.1`, `[::1]` and the `--host` value; any other `Host`
  header gets 400, which prevents a web page from reaching the API through DNS rebinding.
- Watchlists are addressed by name only; file paths are not accepted.

## Examples

```bash
curl -s http://127.0.0.1:8000/api/health

curl -s -X POST http://127.0.0.1:8000/api/backtest \
  -H "Content-Type: application/json" \
  -d '{"ticker": "SPY", "signal": "connors_rsi2_long", "params": {"oversold": 15},
       "settings": {"risk": {"atr_mult": 3}},
       "exits": [{"name": "target", "params": {"target_r": 3}}],
       "filters": [{"name": "trend", "params": {"period": 100}}]}'

curl -s -X POST http://127.0.0.1:8000/api/sweep \
  -H "Content-Type: application/json" \
  -d '{"ticker": "SPY", "signal": "connors_rsi2_long",
       "axes": [{"target": "signal", "name": "oversold", "values": [5, 10, 15, 20]}]}'
```

## Regenerating the frontend types

After changing a model in `api/schemas/`:

```powershell
.venv\Scripts\python scripts\export_openapi.py frontend\openapi.json
npm --prefix frontend run gen:api
```

`export_openapi.py` builds the app with an empty data provider and writes its OpenAPI schema;
`openapi-typescript` turns it into `frontend/src/api/schema.ts`. `frontend/openapi.json` is git-ignored;
`schema.ts` is committed.
