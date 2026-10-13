# tradescan

Trading signal scanner for daily bars: **vectorized pandas signals on yfinance data**, with
**backtrader's Cerebro as an optional second engine** to validate a signal with realistic orders.

- 30 signals in 6 families (trend, momentum, breakout, mean reversion, volume, patterns), long and short
- confluence score: weighted fresh signals + daily trend + weekly trend + relative strength
- risk plan for every setup: ATR stop, 2R/3R targets, position size from account risk
- historical edge of each signal: win rate and forward return vs. the average bar
- market regime: benchmark vs. SMA200, breadth, new highs/lows
- two backtest engines that produce identical trades (pandas for speed, Cerebro as reference)
- a React web UI on top of a small FastAPI server (`tradescan serve`)

> Not investment advice. This is a research tool; every number it prints is a historical statistic.

## Install

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[cerebro,api,dev]"
```

`cerebro` (backtrader) is optional; without it everything except `--engine cerebro` works.
`api` (FastAPI, uvicorn) is only needed for the web UI.

## Web UI

```bash
npm --prefix frontend install
npm --prefix frontend run build
tradescan serve
```

Open http://127.0.0.1:8000. One server delivers both the API (`/api/...`, docs at `/docs`) and
the built UI. The screens:

- **Scanner**: market regime, ranked setups, CSV export; click a row for a candlestick chart with
  signal markers and stop/target lines, the risk plan, the score breakdown and each fired signal's
  history on that ticker.
- **Backtest**: one signal on one ticker with either or both engines; key metrics, equity vs. buy &
  hold, trades on the chart and in a sortable table.
- **Edge**: signal statistics across a watchlist at several horizons, coloured by edge.
- **Signals**: the signal library with families, weights and rules.

Account size, risk per trade and lot size are set from the header and stored in the browser.
Forms live in the URL, so a scan or backtest can be bookmarked or shared.

> The API has no authentication. `serve` binds to 127.0.0.1; do not expose it to a network.

For frontend development run the API and Vite's dev server side by side (Vite proxies `/api`):

```bash
tradescan serve
npm --prefix frontend run dev
```

After changing API models, regenerate the TypeScript types:

```bash
python scripts/export_openapi.py frontend/openapi.json
npm --prefix frontend run gen:api
```

## Usage

Run commands from the project folder, so `config/settings.toml` and `config/watchlists/` are found
(or pass `--config` / `--watchlists-dir`).

```bash
tradescan list-signals
tradescan market -w us_large
tradescan scan -w wig20 --direction long --top 10
tradescan scan -t AAPL,MSFT,PKO.WA --fresh 1 --export exports/hits.csv
tradescan edge -w etf --family breakout,trend --min-events 30
tradescan backtest SPY donchian_breakout --engine both
tradescan scan -w crypto --lot-size 0.0001
```

| Command | What it does |
| --- | --- |
| `scan` | Signals that fired within the last `--fresh` bars, scored and ranked, with stop/target/size and the edge of the most recent signal on that ticker. |
| `market` | Regime label (risk-on / neutral / risk-off) from the benchmark trend and watchlist breadth. |
| `edge` | For each signal, pooled across the watchlist: events, win rate, average and edge vs. baseline at several horizons. |
| `backtest` | One signal on one ticker with the pandas engine, Cerebro, or `both` side by side. |
| `list-signals` | All signals with family, direction, scoring weight and rule. |

Watchlists are text files in `config/watchlists/` (tickers separated by spaces or commas, `#` comments).
A line `# benchmark: SPY` sets the benchmark for that list. Bundled: `us_large`, `wig20`, `etf`, `crypto`.

## How it works

**Signals.** Each signal is a boolean rule evaluated on the bar's close. Only the first bar of each
run counts as an event, so signals can be counted, scored and backtested in the same way. All
indicators are causal; a test checks that adding future bars never changes past signals.

**Score** (per ticker and direction):

```
score = sum(weight of each fresh signal)        # family weights in settings, per-signal overrides
      + trend_bonus  if daily trend agrees  (- if it disagrees)   # close vs SMA200, SMA50 vs SMA200
      + weekly_bonus if weekly trend agrees (- if it disagrees)   # 30-week SMA, Weinstein stage
      + rs_bonus     if relative strength is in the top 20% (long) / bottom 20% (short)
```

Relative strength is IBD-style (40% last quarter, 20% each of the three before) ranked within the
watchlist.

**Risk plan.** Entry = last close, stop = `atr_mult` x ATR(14) away, targets at `targets_r` multiples
of that risk. Size risks `risk_pct` of equity at the stop, capped at `max_position_pct` of equity.

**Edge.** Return from the next bar's open to the close `h` bars after each past event, in the
signal's direction, compared with the same measure over all bars ("vs base").

**Backtests.** Both engines use the same rules:

- a signal on bar t buys/sells at the open of bar t+1, sized from equity at bar t;
- stop and target come from the signal bar's close and ATR;
- stop and target are checked from the bar after the entry bar (as backtrader's bracket orders do);
  if both are touched on the same bar the stop wins; a gap through a level fills at the open;
- a time exit fills at the open `max_hold_bars` bars after entry;
- commission and slippage are percentages, slippage never moves a fill outside the bar's range.

Metrics: total return, CAGR, Sharpe, Sortino, max drawdown, win rate, profit factor, expectancy in R,
SQN, exposure, buy & hold.

## Configuration

`config/settings.toml` holds account size, risk per trade, ATR stop multiple, targets, freshness,
benchmark, scoring weights and backtest costs. Every key is optional and unknown keys are rejected.
Data is cached as Parquet in `.cache/` for `cache_ttl_hours`; use `--no-cache` to force a download.

## Extending

The code follows SOLID; each extension point is a new class, not an edit to existing logic.

- **New signal:** subclass `Signal`, implement `condition`, decorate with `@register`, and import its
  module in `signals/__init__.py`. Scanner, scoring, edge, both engines and the CLI pick it up.

  ```python
  @register
  @dataclass(frozen=True)
  class InsideDayBreakout(Signal):
      name = "inside_day_breakout"
      family = Family.BREAKOUT
      direction = Direction.LONG
      description = "Close above the high of an inside day"

      def condition(self, df: pd.DataFrame) -> pd.Series:
          inside = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))
          return inside.shift(1, fill_value=False) & (df["close"] > df["high"].shift(1))
  ```

- **New data source:** implement the `DataProvider` protocol (`history(tickers, period, interval)`);
  `CachedProvider` wraps any provider.
- **New backtest engine:** implement `BacktestEngine.run` and add it to `default_engines()` in
  `services.py`; the CLI, the API and the UI's engine picker pick it up.
- **New export format:** add a writer to `_WRITERS` in `report/export.py`.
- **New API endpoint:** add a router module under `api/routes/` with `build_router(context)` and list
  it in `ROUTERS` in `api/app.py`.

The use cases in `services.py` (scan, market, edge, backtest, chart) hold the workflow; `cli.py` and
`api/` only translate input and output. `build_use_cases` and `create_app` wire concrete classes.

## Limitations

- During market hours the last daily bar is still forming; run scans after the close.
- Bundled watchlists hold today's index members, so historical edge carries survivorship bias.
- yfinance uses an unofficial Yahoo API (rate limits, format changes; personal use per Yahoo's terms).
  The Yahoo WIG20 index has no history, so `wig20` uses the `ETFBW20TR.WA` ETF as its benchmark.
- backtrader is unmaintained (last release 2023). It works with Python 3.13, pandas 3 and numpy 2
  here, but its `cerebro.plot()` is not used.
- Daily bars cannot show whether the stop or target was hit first inside one bar; the stop is assumed.

## Development

```bash
.venv\Scripts\python -m pytest
npm --prefix frontend test
npm --prefix frontend run typecheck
```

Python tests run on deterministic synthetic data and never touch the network; frontend tests mock
the API.
