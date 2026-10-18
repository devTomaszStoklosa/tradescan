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
- walk-forward analysis: re-tune one or two parameters on rolling in-sample windows, trade each pick on the
  window after it, and join the out-of-sample windows into one equity curve
- a Monte Carlo of every backtest's trades: how deep the drawdown and how long the losing streak could have
  been, and the chance of ruin at the run's risk per trade
- one setup on every ticker of a watchlist: each ticker's metrics, all trades pooled, and how the results spread
- one setup as a portfolio with one shared equity: a cap on open positions and on exposure, a priority when
  more signals fire than fit, and portfolio metrics, with Cerebro as a reference that produces the same trades
- a momentum rotation: the strongest tickers of a watchlist, rebalanced weekly or monthly, with the slots of
  falling picks in a safe asset or cash
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
  RSI, SMA and Supertrend exits, failed breakout and no-progress exits) on top of the ATR stop, and
  pyramiding (more units as the trade moves in its favour); the signal's and the rules' parameters are
  editable; key metrics, equity vs. buy & hold, in-sample vs. out-of-sample metrics, a Monte Carlo of the
  trades, trades on the chart (with every add) and in a sortable table.
- **Sweep**: the same setup as Backtest over a range of one or two of its parameters (signal, filters,
  entry, exits, stop, pyramiding or costs), as two heatmaps of a metric you pick: in-sample and out-of-sample. Click a
  cell for its metrics, the average of its neighbours, and a link that opens it on the Backtest page.
- **Walk-forward**: the same setup and swept parameters as Sweep, re-tuned on every in-sample window and
  traded on the window after it; the window scheme (rolling or anchored), the selection metric, the number
  of windows, their in-sample length and the trades a pick needs are editable. Key metrics of the stitched
  out-of-sample curve against the unchanged setup and buy & hold, the walk-forward efficiency, the curves on
  one chart with the window starts, every window with its pick and the bars it traded, the setting to trade
  next with a link that opens it on the Backtest page, and the out-of-sample trades.
- **Watchlist**: the same setup as Backtest on every ticker of a watchlist (or your own tickers): the
  spread of a metric you pick across the tickers (worst, quartiles, median, best and the share above
  break-even) in-sample and out-of-sample, every ticker's trades pooled in R, and a sortable table of
  each ticker's metrics, where a ticker opens its own backtest.
- **Portfolio**: the same setup as Watchlist, without pyramiding, with one shared equity, on either or
  both engines: the max positions, the max exposure and the priority rule with its parameters are editable (the scan score
  priority also offers the scanner's scoring, trend and fresh-signal settings and each signal's
  parameters and score weight, the traded signal's parameters coming from the setup); key metrics against
  the benchmark's buy & hold, skipped signals, equity and open positions over time, metrics and portfolio
  stats in-sample and out-of-sample, each ticker's contribution (a ticker opens its own backtest) and every
  trade with its ticker. **Pin run** keeps the shown engine's run for Compare.
- **Rotation**: hold the strongest tickers of a watchlist, rebalanced weekly or monthly: the ranking and
  weighting rules with their parameters, the holdings, the absolute momentum lookback, the safe asset,
  the benchmark and the costs are editable; key metrics against the benchmark's buy & hold, the share held
  defensively and the turnover, equity and holdings over time, what a rebalance at the last close would
  pick, metrics and rotation stats in-sample and out-of-sample, each ticker's contribution and every
  holding.
- **Edge**: signal statistics across a watchlist at several horizons, coloured by edge.
- **Compare**: backtest and portfolio runs pinned with **Pin run** on the Backtest and Portfolio pages,
  side by side: the parameters that differ (for a portfolio also its universe, max positions, max exposure
  and priority rule with its parameters), an out-of-sample check (key metrics in-sample next to
  out-of-sample), a Monte Carlo check (unlucky and median return, drawdown and losing streak, and the
  chance of ruin, per method), every metric of the full history or of one period with the best value
  highlighted, the portfolio stats (open positions, exposure, skipped signals) of the same period, and the
  return curves on one chart.
- **Signals**: the signal library with families, weights, rules and each parameter's default and range.

Scanner and Edge have an **Advanced settings** panel with every other parameter (see
[Parameters](#parameters)). Account size, risk per trade, max position and lot size are set from the
header and stored in the browser. Forms, including changed parameters, live in the URL, so a scan or
backtest can be bookmarked, shared or opened in two tabs to compare.

Up to 8 runs can be pinned. A pinned run is a snapshot: it keeps the result you saw even after new bars
arrive, and **Open in Backtest** (or **Open in Portfolio**) runs it again with today's data and the
account currently set in the header. Pinned runs live in this browser only (clearing site data deletes them), so use **Export JSON**
as a backup or to move them to another browser, and **Import JSON** to bring them back. Runs with fewer
than 20 trades are flagged, because their metrics are mostly noise. Runs pinned before out-of-sample or
Monte Carlo results existed have none, since a pin is never re-run; portfolio runs have no Monte Carlo.

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
tradescan backtest QQQ donchian_breakout --exits trailing --max-units 4 --add-every-atr 0.5 --engine both
tradescan backtest SPY connors_rsi2_long --exits rsi,time --engine both
tradescan backtest QQQ donchian_breakout --entry stop --exits failed_breakout,no_progress,trailing
tradescan backtest AAPL donchian_breakout --filters trend,market,volume --benchmark QQQ
tradescan backtest SPY connors_rsi2_long --oos 20
tradescan sweep SPY connors_rsi2_long --axis signal.oversold=4:16:2 --axis exit.target.target_r=1,2,3 --metric expectancy_r
tradescan walk-forward SPY connors_rsi2_long --axis signal.oversold=5:25:2.5 --axis exit.target.target_r=1:3:0.5 --windows 5
tradescan watchlist-backtest connors_rsi2_long -w etf --filters market --metric expectancy_r
tradescan portfolio-backtest donchian_breakout -w sp500 --filters trend --max-positions 10 --priority momentum
tradescan rotation-backtest -w etf --holdings 3 --weighting inverse_volatility --safe-asset TLT
tradescan scan -w crypto --lot-size 0.0001
tradescan update-universes
```

| Command | What it does |
| --- | --- |
| `scan` | Signals that fired within the last `--fresh` bars, scored and ranked, with stop/target/size and the edge of the most recent signal on that ticker. |
| `market` | Regime label (risk-on / neutral / risk-off) from the benchmark trend and watchlist breadth. |
| `edge` | For each signal, pooled across the watchlist: events, win rate, average and edge vs. baseline at several horizons. |
| `backtest` | One signal on one ticker with the pandas engine, Cerebro, or `both` side by side, plus its in-sample and out-of-sample metrics. `--filters` picks the entry filters (none by default) and `--benchmark` the benchmark the market filter compares, `--entry` the entry rule, `--exits` the exit rules (`none` keeps only the stop), `--max-units` and `--add-every-atr` the pyramiding, `--oos` the out-of-sample share. |
| `sweep` | The `backtest` setup over one or two `--axis` parameters (`target[.owner].name=FROM:TO:STEP` or `=V1,V2,...`), as in-sample and out-of-sample grids of `--metric`; `--export` saves every combination. |
| `walk-forward` | The `backtest` setup with one or two `--axis` parameters as in `sweep`, re-tuned on `--windows` in-sample windows `--in-sample-ratio` times as long as the out-of-sample windows after them (`--scheme rolling` or `anchored`), each window picking the highest in-sample `--metric` with at least `--min-trades` trades: every window with its pick, the stitched out-of-sample metrics next to the unchanged setup, the walk-forward efficiency and the next setting; `--export` saves every window with both periods' metrics. |
| `watchlist-backtest` | The `backtest` setup (without the ticker) on every ticker of `-w`/`-t` with the vectorized engine: the best `--top` tickers by `--metric` with their in-sample and out-of-sample values, the spread of `--metric` across tickers and all trades pooled; `--export` saves every ticker with every period's metrics. |
| `portfolio-backtest` | The `backtest` setup (without the ticker and without pyramiding) on every ticker of `-w`/`-t` with one shared equity: `--max-positions` and `--max-exposure` (% of equity) cap it, `--priority` ranks the signals when more fire than fit (`score` reads `[scoring]`, `[trend]` and `[scan] fresh_bars` from the settings file), `--engine` picks the engine (or `both`). Prints every engine's metrics and portfolio stats for the full history and both periods and the `--top` tickers by P&L; `--export` saves every engine's trades. |
| `rotation-backtest` | A momentum rotation over every ticker of `-w`/`-t`: `--rank` ranks them (default `momentum`), `--holdings` picks the top N, `--rebalance` is `weekly` or `monthly` (default), `--weighting` is `equal` (default) or `inverse_volatility`, `--absolute-lookback` sets the absolute momentum check (0 turns it off) and `--safe-asset` takes the slots of the picks that fail it (default cash). Prints the metrics and rotation stats for the full run and both periods, what a rebalance at the last close would pick and the `--top` tickers by P&L; `--export` saves the trades. |
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

**Pyramiding.** With `pyramid.max_units` above 1 (default 1: off), a position that moves in the trade's
favour adds units, Turtle style:

- once the first unit has filled, a stop order for one more unit waits at every close
  `pyramid.add_every_atr` ATRs (default 0.5) beyond the previous unit's fill, until the position holds
  `max_units` units. The ATR is the signal bar's, the one that sized the first unit, so the units stay
  evenly spaced; a gap through the level fills at the open, and the next add counts from that fill;
- every add is the size of the first unit, so `max_position_pct` caps each unit, not the position;
- after an add fills, the stop of the whole position moves to `atr_mult` ATRs from that fill. Together
  with the initial stop and the exit rules, the tightest stop applies;
- the exit rules close the whole position and measure from the first unit: the target from its
  reference, the breakeven stop and the no-progress exit from its fill, the time exit from its entry bar.
  On a bar where the position exits, no unit is added;
- a trade is the whole position: its entry date is the first fill, its entry price the average fill of
  its units, its size and P&L all units', and its R multiple the P&L in units of one unit's risk at the
  initial stop, so 1R is the same loss with and without pyramiding. Each trade lists its adds (date and
  price); the trades table shows the units and the chart marks every add.

Both engines pyramid the same way. Neither refuses a fill for lack of cash (Cerebro's broker is set up as
in the portfolio backtest), so several units can be worth more than the equity. Sweeps, walk-forwards and
watchlist backtests pyramid too; the portfolio backtest and the rotation do not, and a portfolio backtest with
`max_units` above 1 is refused.

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

**Monte Carlo.** Every backtest also resamples the full history's closed trades in R, for each engine,
to show how much of the result is the luck of the order and of the sample. Each simulated sequence is
traded with fixed-fractional sizing: a trade moves equity by `account.risk_pct` percent times its R.

- shuffled: the same trades in a random order. The final return is the same for every order, so this
  spreads the maximum drawdown and the longest losing streak;
- bootstrapped: as many trades drawn at random with replacement, which spreads the final return too.

For each method the Backtest page shows the unlucky (5th percentile on the bad side), median and lucky
(95th percentile) final return, maximum drawdown and longest losing streak next to the run's own order of
trades, and the chance of ruin: the share of simulations whose drawdown from the peak reaches
`monte_carlo.ruin_drawdown_pct` (default 50%). `monte_carlo.simulations` (default 1000 per method) and
`monte_carlo.seed` (the same seed repeats the same simulations) are settable too. The model leaves out
the cap on position value and any trade still open on the last bar, so its numbers differ from the
backtest's own. A run needs at least two closed trades; sweeps, walk-forwards and watchlist backtests run
no Monte Carlo. The API reports it as `monte_carlo` on every run of `/api/backtest`.

**Sweeps.** A sweep runs one setup for every combination of one or two parameters' values (at most 200
combinations, 2–50 values per parameter), each on both periods, with the pandas engine on all CPU cores.
Any single-number parameter of the signal, the setup's entry filters, the entry rule, the setup's exit
rules or the `account`, `risk`, `backtest` and `pyramid` settings can be swept; the out-of-sample share cannot,
since it defines the split. A combination that breaks a rule between parameters (for example a fast
average that is not shorter than the slow one) is shown as failed and the others still run. On 10 years
of daily bars a sweep of 200 combinations takes a few seconds.

**Walk-forward.** A walk-forward re-tunes one setup over and over and trades each setting only on history
it was not tuned on. It takes the same one or two swept parameters as a sweep and runs on the pandas engine
on all CPU cores:

- **windows:** the history is cut into `walk_forward.windows` out-of-sample windows of equal length (default
  5) that end on the last bar. Each one follows an in-sample window `walk_forward.in_sample_ratio` times as
  long (default 3): `rolling` in-sample windows keep that length and slide along, `anchored` ones start on
  the first bar and grow. Every window needs at least 60 bars, and the bars before the first in-sample
  window (fewer than the windows plus the ratio) only warm indicators up. 10 years of daily bars with the
  defaults give windows of about 315 bars after in-sample windows of about 945;
- **picks:** every combination runs on every in-sample window, the way the in-sample period of a backtest
  runs: the engine gets the bars up to the window's end, the signal fires from its start, and the metrics
  start there. The window picks the combination with the highest selection metric (default Sharpe; any
  metric but the trade count, the exposure and buy & hold) among those with at least
  `walk_forward.min_trades` closed trades (default 10). Ties go to the first combination in grid order. A
  window where no combination qualifies holds cash;
- **stitching:** each window's pick trades its out-of-sample window with the equity the window before
  ended with, its signal firing only within the window. A position still open at the end of a window runs
  to its own exit under that window's setting, and the next window trades from the bar of that exit on, so
  a window can start late, or never trade when a position runs past its end. The windows join into one
  equity curve; only the last window can end with an open position;
- **reported:** the metrics of the stitched curve, next to the unchanged setup (the setup with the values as
  set, traded on the same bars from the first out-of-sample bar on) and buy & hold; the walk-forward
  efficiency, the stitched out-of-sample CAGR over the average in-sample CAGR of the picks (Pardo; it is
  left out when that average is not above 0); each window's dates, pick, in-sample and out-of-sample value
  of the metric, trades and return, and the bars its pick traded; the out-of-sample trades; and the next
  setting, picked on the in-sample window that ends on the last bar.

The out-of-sample share has no effect in a walk-forward, and the account equity cannot be swept, since each
window starts with the equity the one before it ended with. Every combination runs once per in-sample
window, the next one included, and a walk-forward runs at most 2000 backtests: on 10 years of daily bars
that takes 10–20 s. Picks that change from window to window, or an efficiency far below 1, mean the best
in-sample setting does not carry forward: the in-sample peaks were luck.

**Watchlist backtests.** One setup runs on every ticker of a watchlist, with the pandas engine on all CPU
cores. Each ticker is split on its own bars as a backtest of it alone would be, so a ticker's row is that
ticker's backtest; a ticker with too little history to split has only full-history metrics. The market
filter compares the setup's benchmark, else the watchlist's (`# benchmark:`), else `scan.benchmark`.

- **Spread:** for every metric and period, the worst, 25%, median, 75% and best value across the tickers,
  and the share above break-even (0 for returns, Sharpe, Sortino, expectancy and SQN, 1 for the profit
  factor). Tickers without a value, e.g. without trades, are left out.
- **Pooled trades:** every ticker's closed trades taken together, in R: win rate, expectancy, profit
  factor (R won / R lost) and SQN. Profits in money are not pooled, since each ticker's equity compounds
  on its own.

A setting that works on one or two tickers and not on the rest is fitted to them. On 20 ETFs with
10 years of daily bars a watchlist backtest takes a few seconds once the data is cached.

**Portfolio backtests.** One setup runs on every ticker of a watchlist with one shared equity, on the
pandas engine, Cerebro or both, which produce the same trades. Every ticker trades by the rules above,
without pyramiding, on its own bars; the portfolio decides at each close of the shared calendar (every date on which a ticker has
a bar):

- a ticker whose entry order waits or whose position is open ignores its signals, as in a single backtest;
- the signals of the other tickers are ranked by the priority rule, the highest score first; ties keep the
  watchlist order, and signals without a score (too little history) go last;
- a signal gets an entry order while open positions plus waiting orders stay below
  `portfolio.max_positions` (default 10); a waiting order holds its slot until it fills or expires;
- its size comes from the shared equity, marked to market at each ticker's last close, with the account's
  risk per trade, max position and lot size. When its value at the entry reference would take the gross
  exposure (open positions at the close plus waiting orders at their reference) above
  `portfolio.max_exposure_pct` of equity (default 100%; above it is leverage), it is cut to fit, and
  skipped when less than one lot fits. A gap can fill a position above its value at the reference, so
  exposure can end slightly above the cap;
- signals skipped for want of a slot or of exposure room are counted.

| Priority | Score, the highest first |
| --- | --- |
| `relative_strength` (default) | the returns over `periods` bars times their `weights` (default 63/126/189/252 bars weighted 0.4/0.2/0.2/0.2, IBD style); for shorts the lowest first |
| `momentum` | the return from `lookback` bars ago to `skip` bars ago (default 252 and 21: 12-1 month momentum); for shorts the lowest first |
| `score` | the scan's confluence score for the signal's direction at that close: the weights of the signals of that direction that fired within `scan.fresh_bars` bars, the daily and weekly trend bonuses and the relative-strength bonus, with relative strength ranked among the watchlist's tickers that have a bar at that close |

The `score` priority has no parameters of its own: it reads the run's `[scoring]`, `[trend]` and
`scan.fresh_bars` settings, so it scores like a scan with the same settings, and a run can override them
like any setting. Every registered signal of the direction counts, the traded one with the run's
parameters and the others with the run's `score_signal_params` (on the Portfolio page, each signal's
parameters under Scan score settings, `ss.<signal>.<name>` in the URL), else their defaults; an entry for
the traded signal or the other direction is checked and changes nothing. Its scores move in steps of the
weights and bonuses, so ties are common; tied signals keep the watchlist order. It reads every signal on
every ticker once per run, about 0.1 s per ticker of 10 years.

The metrics are a backtest's on the shared equity, except that buy & hold is the benchmark's (the setup's,
else the watchlist's, else `scan.benchmark`) and exposure is the share of days with an open position. The
portfolio also reports the average and highest open positions and gross exposure, the entry orders, the
skipped signals, and each ticker's trades, P&L and share of the result. The shared calendar is split
in-sample and out-of-sample like a single backtest's history: the in-sample run gets the bars before the
split date, the out-of-sample run every bar with signals from the split date on and fresh equity. A ticker
whose bars end early keeps a position that is still open, marked to its last close, until the end.

Cerebro runs every ticker as a data feed of one strategy with the same allocation code. Its broker never
refuses a fill for lack of cash, so the exposure cap is the only limit on size, and tries an order only on
a bar of its ticker after the one it was placed on. It is the reference and is slow: about a minute per
20 tickers of 10-year history. The pandas engine runs the S&P 500 over 10 years in under a minute once the
data is cached.

**Momentum rotation.** A rotation holds the strongest tickers of a watchlist with one shared equity,
without signals or stops. At the close of the last day of every week or month of the shared calendar
(`weekly` or `monthly`; the last week or month of the data may go on, so it never rebalances):

- the ranking rule ranks every ticker that still trades, by its last bar on a day without one of its own.
  The rankings are the priority rules that read bars only: `momentum` (default; 12-1 month momentum) and
  `relative_strength` (IBD style), with the parameters in the priority table above;
- the top `rotation.holdings` tickers are picked (default 5). With `rotation.absolute_lookback` above 0
  (default 252 bars), a pick whose return over that many bars is at or below 0 hands its slot to the safe
  asset, or to cash without one. The safe asset is held even when its own momentum is negative, and can
  be one of the watchlist's tickers;
- the weighting rule shares the equity among the picks: each pick averages one slot of
  1 / `holdings`, so a full book is 100% of equity, and slots without a pick stay in cash;
- target shares are a pick's share of the equity at the close divided by its close, rounded down to lots.
  Only the difference to the shares held trades, with a market order for the next open at the backtest's
  slippage and commission. Cash never limits a fill, so a gap can take the holdings slightly above 100%;
  an order whose ticker has no bar before the next rebalance is dropped and counted.

| Weighting | Share of the book |
| --- | --- |
| `equal` (default) | one slot per pick |
| `inverse_volatility` | in proportion to 1 / the standard deviation of the pick's daily returns over `lookback` bars (default 63); a ticker whose closes did not move has none and cannot be picked |

A trade is a holding: from the buy that opens a position to the sale that empties it at a rebalance, with
every add, trim and commission in its P&L and the average prices of its buys and sales. Holdings have no
stop and so no R multiple, which leaves expectancy and SQN empty; the win rate and profit factor count the
holdings. The run starts at the close of the first rebalance at which a ticker can be picked, so the
warm-up of the lookbacks does not count as time in cash, and buy & hold compares the benchmark over the
same dates. Its dates are split in-sample and out-of-sample: the in-sample run gets the bars before the
split, the out-of-sample run every bar, rebalancing from the split on with fresh equity and lookbacks that
are already warm. The rotation also reports the average holdings, the shares of equity invested, in the
safe asset and in cash, the yearly turnover (half the value traded, in % of the average equity), the
commissions, and what a rebalance at the last close would pick. Cash earns nothing. A ticker whose bars
end early keeps what it holds, marked to its last close, and the rebalances share out the rest. Only the
pandas engine runs rotations: 20 ETFs over 10 years take about a second once the data is cached.

## Configuration

`config/settings.toml` holds account size, risk per trade, ATR stop multiple, targets, freshness,
benchmark, scoring weights, trend and relative-strength lookbacks, market regime thresholds,
backtest costs, pyramiding, the Monte Carlo of a backtest's trades, a portfolio's limits and a rotation's holdings and
absolute momentum. Every key is optional; unknown keys and values outside a parameter's range are rejected.
Data is cached as Parquet in `.cache/` for `cache_ttl_hours`; use `--no-cache` to force a download.

## Parameters

Every number that changes a result is a declared parameter with a default, an allowed range and a label:
the settings of all 38 signals (periods, thresholds, multipliers), of the backtest's entry filters,
entry rules and exit rules, and the settings sections `account`, `risk`, `scan`, `scoring`, `trend`,
`regime`, `backtest`, `pyramid`, `monte_carlo`, `portfolio` and `rotation`. `settings.toml` holds the defaults of the settings sections, the code those of
signals and rules; a single run can override any of them without touching the file:

- in the web UI, where changed values are highlighted, kept in the URL and checked against their range;
- through the API: `"settings": {"risk": {"atr_mult": 3}}` and
  `"signal_params": {"connors_rsi2_long": {"oversold": 15}}` (a backtest takes its signal's values as
  `"params"`, and its rules as `"entry": {"name": "limit", "params": {"offset_atr": 1}}`,
  `"exits": [{"name": "target", "params": {"target_r": 3}}]` and
  `"filters": [{"name": "trend", "params": {"period": 100}}]` with `"benchmark": "QQQ"`), a sweep its
  parameters as `"axes": [{"target": "exit", "owner": "target", "name": "target_r", "values": [1, 2, 3]}]`,
  and a watchlist backtest (`/api/watchlist-backtest`) the same setup with `"watchlist": "etf"` or
  `"tickers": [...]` instead of the ticker, as does a portfolio backtest (`/api/portfolio-backtest`) with
  `"priority": {"name": "momentum", "params": {"skip": 0}}` and `"engines"`; the `score` priority takes
  `"settings": {"scoring": {...}, "trend": {...}, "scan": {"fresh_bars": 5}}` and the other signals'
  parameters as `"score_signal_params": {"donchian_breakout": {"period": 55}}`); a rotation
  (`/api/rotation-backtest`) takes the universe, `"ranking"` and `"weighting"` rules with their
  `"params"`, `"rebalance": "weekly"`, `"safe_asset": "TLT"` and `"settings": {"rotation": {"holdings": 3}}`;
  `/api/config` lists the settings, the rules and the sweep limits, `/api/signals` the signals, each
  parameter with its range;
- on the CLI, through the existing flags (`--atr-mult`, `--fresh`, `--equity`, `--target-r`, `--max-units`, `--oos`, ...).

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
- **New ranking or weighting rule:** a rotation ranks by any priority rule that does not read the scanner
  (subclass `TickerPriorityRule` in `backtest/priority.py` and return each close's strength from
  `strength`), and weights by any `WeightRule` (in `backtest/weighting.py`) that returns each close's raw
  weight from `raw`. Register it with `@priority_rules.register` or `@weight_rules.register`.
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
