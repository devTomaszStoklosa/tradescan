cd C:\Users\Tomasz\Desktop\Repo\Backtrader
npm --prefix frontend install
npm --prefix frontend run build
tradescan serve

# tradescan

Trading signal scanner for daily bars: **vectorized pandas signals on yfinance data**, with
**backtrader's Cerebro as an optional second engine** to validate a signal with realistic orders.

- 38 signals in 6 families (trend, momentum, breakout, mean reversion, volume, patterns), long and short
- confluence score: weighted fresh signals + daily trend + weekly trend + relative strength
- risk plan for every setup: ATR stop, 2R/3R targets, position size from account risk
- historical edge of each signal: win rate and forward return vs. the average bar
- market regime: benchmark vs. SMA200, breadth, new highs/lows
- two backtest engines that produce identical trades (pandas for speed, Cerebro as reference)
- an out-of-sample check on every backtest, and parameter sweeps shown as in-sample and out-of-sample heatmaps
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
- **Backtest**: one signal on one ticker with either or both engines; pick the entry filters a signal
  has to pass (trend, market, ADX, volume, ATR% band, with a benchmark for the market filter), the entry
  (next open, stop or limit order) and the exits (target, time exit, trailing, channel and breakeven stops,
  RSI, SMA and Supertrend exits, failed breakout and no-progress exits) on top of the ATR stop; the
  signal's and the rules' parameters are editable; key metrics, equity vs. buy & hold, in-sample vs.
  out-of-sample metrics, trades on the chart and in a sortable table.
- **Sweep**: the same setup as Backtest over a range of one or two of its parameters (signal, filters,
  entry, exits, stop or costs), as two heatmaps of a metric you pick: in-sample and out-of-sample. Click a
  cell for its metrics, the average of its neighbours, and a link that opens it on the Backtest page.
- **Edge**: signal statistics across a watchlist at several horizons, coloured by edge.
- **Compare**: backtest runs pinned with **Pin run** on the Backtest page, side by side: the parameters
  that differ, an out-of-sample check (key metrics in-sample next to out-of-sample), every metric of the
  full history or of one period with the best value highlighted, and the return curves on one chart.
- **Signals**: the signal library with families, weights, rules and each parameter's default and range.

Scanner and Edge have an **Advanced settings** panel with every other parameter (see
[Parameters](#parameters)). Account size, risk per trade, max position and lot size are set from the
header and stored in the browser. Forms, including changed parameters, live in the URL, so a scan or
backtest can be bookmarked, shared or opened in two tabs to compare.

Up to 8 runs can be pinned. A pinned run is a snapshot: it keeps the result you saw even after new bars
arrive, and **Open in Backtest** runs it again with today's data and the account currently set in the
header. Pinned runs live in this browser only (clearing site data deletes them), so use **Export JSON**
as a backup or to move them to another browser, and **Import JSON** to bring them back. Runs with fewer
than 20 trades are flagged, because their metrics are mostly noise. Runs pinned before out-of-sample
results existed have none, since a pin is never re-run.

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
tradescan scan -w sp500 --min-score 4
tradescan scan -w wig20 --direction long --top 10
tradescan scan -t AAPL,MSFT,PKO.WA --fresh 1 --export exports/hits.csv
tradescan edge -w etf --family breakout,trend --min-events 30
tradescan backtest SPY donchian_breakout --engine both
tradescan backtest SPY connors_rsi2_long --entry limit --exits time --max-hold 5
tradescan backtest QQQ donchian_breakout --exits trailing,breakeven
tradescan backtest SPY connors_rsi2_long --exits rsi,time --engine both
tradescan backtest QQQ donchian_breakout --entry stop --exits failed_breakout,no_progress,trailing
tradescan backtest AAPL donchian_breakout --filters trend,market,volume --benchmark QQQ
tradescan backtest SPY connors_rsi2_long --oos 20
tradescan sweep SPY connors_rsi2_long --axis signal.oversold=4:16:2 --axis exit.target.target_r=1,2,3 --metric expectancy_r
tradescan scan -w crypto --lot-size 0.0001
tradescan update-universes
```

| Command | What it does |
| --- | --- |
| `scan` | Signals that fired within the last `--fresh` bars, scored and ranked, with stop/target/size and the edge of the most recent signal on that ticker. |
| `market` | Regime label (risk-on / neutral / risk-off) from the benchmark trend and watchlist breadth. |
| `edge` | For each signal, pooled across the watchlist: events, win rate, average and edge vs. baseline at several horizons. |
| `backtest` | One signal on one ticker with the pandas engine, Cerebro, or `both` side by side, plus its in-sample and out-of-sample metrics. `--filters` picks the entry filters (none by default) and `--benchmark` the benchmark the market filter compares, `--entry` the entry rule, `--exits` the exit rules (`none` keeps only the stop), `--oos` the out-of-sample share. |
| `sweep` | The `backtest` setup over one or two `--axis` parameters (`target[.owner].name=FROM:TO:STEP` or `=V1,V2,...`), as in-sample and out-of-sample grids of `--metric`; `--export` saves every combination. |
| `list-signals` | All signals with family, direction, scoring weight and rule. |
| `update-universes` | Refresh the `sp500` and `nasdaq100` watchlists from Wikipedia's constituent tables (`--only sp500`). |
| `serve` | Web UI and HTTP API. |

Watchlists are text files in `config/watchlists/` (tickers separated by spaces or commas, `#` comments).
A line `# benchmark: SPY` sets the benchmark for that list. Bundled: `sp500` (503, benchmark SPY),
`nasdaq100` (101, benchmark QQQ), `us_large`, `wig20`, `etf`, `crypto`.

### Index universes

`sp500` and `nasdaq100` are generated from Wikipedia's constituent tables; each file records the source
and date in its header. Index members change every quarter, so refresh them now and then with
`tradescan update-universes`. It prints added and removed tickers, converts share classes to Yahoo's
format (`BRK.B` becomes `BRK-B`), and keeps the existing file if the download or the sanity check fails.

Large universes are processed on all CPU cores (universes of 40 tickers or more). On a 4-core machine
an S&P 500 scan takes about 30 s and the 10-year edge table about 35 s once the data is cached; the first
run downloads every ticker and takes 1–2 minutes. Data is cached per ticker, so `nasdaq100` reuses
what `sp500` already downloaded.

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

**Backtests.** A backtest combines entry filters (none by default), one entry rule and any number of
exit rules on top of an initial ATR stop. Both engines read the same precomputed levels and execute them
the same way:

| Filter | A signal on bar t may trade when |
| --- | --- |
| `trend` | the close is above SMA(`period`) (below it for shorts) |
| `market` | the benchmark's close is above its SMA(`period`) (below it for shorts) |
| `adx` | ADX(`period`) is at least `min_adx`, in either direction |
| `volume` | the bar's volume is at least `min_ratio` x the average of the `period` bars before it |
| `atr_pct` | the ATR (of `risk.atr_period`) is between `min_pct` and `max_pct` % of the close; `min_pct` must be below `max_pct` |

| Entry | Order placed when the signal fires on bar t | Stop and target measured from |
| --- | --- | --- |
| `next_open` (default) | market order for the open of bar t+1 | the signal bar's close |
| `stop` | buy-stop `offset_atr` ATRs above bar t's high (sell-stop below its low for shorts), active `valid_bars` bars | the order level |
| `limit` | buy-limit `offset_atr` ATRs below bar t's close (sell-limit above it for shorts), active `valid_bars` bars | the order level |

| Exit | Closes the trade |
| --- | --- |
| initial stop (always on) | at `atr_mult` x ATR from the reference price; it sizes the trade and defines 1R |
| `target` (default) | with a limit order `target_r` R from the reference price |
| `time` (default) | at the open `max_hold_bars` bars after the entry bar |
| `trailing` | with a stop `atr_mult` x ATR (of each bar) below the highest high since the entry bar (above the lowest low for shorts) |
| `channel` | with a stop at the lowest low of the last `period` bars, bars before the entry included (the highest high for shorts) |
| `breakeven` | with a stop at `lock_r` R from the fill price, once the high since the entry bar (the low for shorts) has reached `trigger_r` R from it; `lock_r` must be below `trigger_r` |
| `rsi` | at the next open once RSI(`period`) closes at or above `level` (at or below 100 - `level` for shorts) |
| `sma_revert` | at the next open once the close is above SMA(`period`) (below it for shorts): the mean-reversion exit |
| `sma_trend` | at the next open once the close is below SMA(`period`) (above it for shorts): the trend-break exit |
| `supertrend` | at the next open once Supertrend(`period`, `mult`) points against the trade |
| `failed_breakout` | at the next open once one of the first `within_bars` closes, the entry bar's included, is more than `buffer_atr` x ATR (of that bar) below the entry reference (above it for shorts) |
| `no_progress` | at the next open if the close `after_bars` bars in, the entry bar counted as the first, has gained less than `min_r` R from the fill price |

- every chosen filter has to allow a signal at the close of its bar. A blocked signal is ignored, like one
  without a price or size, even when the filter allows the next bars, and bars where a filter's indicator
  has too little history block signals. Tickers without volume (indices, some FX) never pass the volume filter;
- the market filter compares the backtest's `benchmark` (default `scan.benchmark`, SPY), which is loaded
  only when a filter needs it. Its SMA is computed on the benchmark's own bars, and each ticker date takes
  the benchmark's last close at or before it, so a ticker that trades on other days (crypto, another
  exchange) still gets a value;
- the trailing, channel and breakeven stops are set at each close for the next bar and only ever tighten.
  Together with the initial stop and each other, the tightest stop applies, so they only matter once
  they are tighter than the initial stop. The high since the entry bar includes the entry bar itself,
  also the part of it before a stop or limit entry filled. A level beyond the close exits at the next open;
- the RSI, SMA and Supertrend exits check their condition at every close from the entry bar on, so a
  trade whose entry bar already meets it (say `sma_revert` after a trend entry) leaves at the next open.
  The close has to be strictly beyond the average, and bars before an indicator has enough history never
  exit. An exit at the open comes before the stop and the target of that bar;
- the failed breakout exit compares closes with the entry reference: the signal bar's close for a next-open
  entry, the order level for a stop entry. After a limit entry the reference lies below the close (above it
  for shorts), so there it only catches a further drop. The no-progress exit checks a single close and
  leaves at the same open as a time exit of `after_bars` bars would; a close exactly `min_r` R up stays in;
- each trade records why it closed: `stop` (the initial stop), the name of the exit rule that closed it
  (`target`, `time`, `trailing`, `channel`, `breakeven`, `rsi`, `sma_revert`, `sma_trend`, `supertrend`,
  `failed_breakout`, `no_progress`), or `open` (still open on the last bar);
- the size risks `risk_pct` of equity at bar t at the initial stop; signals are ignored while an entry
  order waits or a position is open, and an order that does not fill in time is cancelled;
- exit orders are placed on the entry bar and checked from the next bar (as backtrader's bracket orders
  are); if a bar touches both the stop and the target, the stop wins; a gap through a level fills at the open;
- commission and slippage are percentages; slippage never moves a fill outside the bar's range, and a
  limit order never fills worse than its level.

Metrics: total return, CAGR, Sharpe, Sortino, max drawdown, win rate, profit factor, expectancy in R,
SQN, exposure, buy & hold.

**Out-of-sample split.** Every backtest also reports its metrics for two periods, split at
`backtest.oos_pct` (default 30%) from the end of the history:

- in-sample: the engine only gets the bars before the split, so nothing after it can influence the result;
- out-of-sample: the engine gets the full history, so indicators are warmed up, but the signal only fires
  from the split on; the period starts with fresh equity and its metrics start at the split bar.

Each period needs at least 60 bars; with less history the split is left out. Tune on the in-sample
period and treat the out-of-sample one as the check: a setting that only works in-sample is fitted to
the past.

**Sweeps.** A sweep runs one setup for every combination of one or two parameters' values (at most 200
combinations, 2–50 values per parameter), each on both periods, with the pandas engine on all CPU cores.
Any single-number parameter of the signal, the setup's entry filters, the entry rule, the setup's exit
rules or the `account`, `risk` and `backtest` settings can be swept; the out-of-sample share cannot,
since it defines the split. A combination that breaks a rule between parameters (for example a fast
average that is not shorter than the slow one) is shown as failed and the others still run. On 10 years
of daily bars a sweep of 200 combinations takes a few seconds.

## Configuration

`config/settings.toml` holds account size, risk per trade, ATR stop multiple, targets, freshness,
benchmark, scoring weights, trend and relative-strength lookbacks, market regime thresholds and
backtest costs. Every key is optional; unknown keys and values outside a parameter's range are rejected.
Data is cached as Parquet in `.cache/` for `cache_ttl_hours`; use `--no-cache` to force a download.

## Parameters

Every number that changes a result is a declared parameter with a default, an allowed range and a label:
the settings of all 38 signals (periods, thresholds, multipliers), of the backtest's entry filters,
entry rules and exit rules, and the settings sections `account`, `risk`, `scan`, `scoring`, `trend`,
`regime` and `backtest`. `settings.toml` holds the defaults of the settings sections, the code those of
signals and rules; a single run can override any of them without touching the file:

- in the web UI, where changed values are highlighted, kept in the URL and checked against their range;
- through the API: `"settings": {"risk": {"atr_mult": 3}}` and
  `"signal_params": {"connors_rsi2_long": {"oversold": 15}}` (a backtest takes its signal's values as
  `"params"`, and its rules as `"entry": {"name": "limit", "params": {"offset_atr": 1}}`,
  `"exits": [{"name": "target", "params": {"target_r": 3}}]` and
  `"filters": [{"name": "trend", "params": {"period": 100}}]` with `"benchmark": "QQQ"`), and a sweep its
  parameters as `"axes": [{"target": "exit", "owner": "target", "name": "target_r", "values": [1, 2, 3]}]`);
  `/api/config` lists the settings, the rules and the sweep limits, `/api/signals` the signals, each
  parameter with its range;
- on the CLI, through the existing flags (`--atr-mult`, `--fresh`, `--equity`, `--target-r`, `--oos`, ...).

Values outside the range, unknown names and anything that is not a parameter (paths, cache settings)
are refused. Signal descriptions are filled in from the values in use, so "RSI(3) < 15" always
describes the rule that ran.

> Every adjustable setting is also a way to fit the past. Compare variations over a long history and
> several tickers, and distrust a setting that only works within a narrow range: a sweep's heatmaps show
> both. Looking at the out-of-sample results again and again while tuning slowly turns them into
> in-sample results too.

## Extending

The code follows SOLID; each extension point is a new class, not an edit to existing logic.

- **New signal:** subclass `Signal`, implement `condition`, decorate with `@register`, and import its
  module in `signals/__init__.py`. Scanner, scoring, edge, both engines, the CLI and the UI pick it up.
  Declare every number as a field with `param(...)` and use it in the `description` template; a test
  fails otherwise, so the UI can always offer it.

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

- **New entry filter, entry or exit rule:** subclass `EntryFilter` (in `backtest/filters.py`) and return
  from `allows` whether a signal at each bar's close may trade (set `needs_benchmark` when it reads the
  benchmark's closes), subclass `EntryRule` (in `backtest/entries.py`) and return the order type and level
  for every bar from `orders`, or subclass `ExitRule` (in `backtest/exits.py`) and return a tracker from
  `prepare` that names, at every close, the stop level, target level or exit at the next open it wants.
  Register it with `@entry_filters.register`, `@entry_rules.register` or `@exit_rules.register` and declare
  its numbers with `param(...)`. Both engines, the API, the CLI and the UI pick it up, and the engine-parity
  test runs it on both engines.
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
- Bundled watchlists hold today's index members, so historical edge carries survivorship bias: stocks
  that dropped out of the S&P 500 or Nasdaq-100 are missing from the statistics.
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
