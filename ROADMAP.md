# Roadmap

Where tradescan is heading: from single-signal backtests on one ticker towards complete breakout,
mean-reversion, trend and rotation strategies whose every parameter can be compared in the web UI.

Item codes start with a letter for their area:

| Letter | Area |
| --- | --- |
| F | foundation: parameters, rules, engines |
| C | comparing runs |
| O | optimization and validation |
| B | breakout strategies |
| M | mean-reversion strategies |
| T | trend strategies |
| R | rotation strategies |

Numbers are kept once given, so a gap (O5) is not a missing item.

**Keeping it current:** an item gets its GitHub issue when work on it starts, and the item's pull request
updates its row here. Every item declares its parameters with `param(...)`, so the API, the web UI, the
URL, pinned runs, Compare and the sweep pick them up.

## Items

| Code | Item | Status | Size | Needs |
| --- | --- | --- | --- | --- |
| F0 | Every parameter settable in the web UI | done ([#4], [PR #6]) | | |
| C1 | Compare pinned runs side by side | done ([#7], [PR #8]) | | F0 |
| F1 | Entry and exit rules | done ([#10], [PR #11]) | | F0 |
| O1 | Parameter sweep and out-of-sample split | done ([#12], [PR #13]) | | F1 |
| T1 | Trailing, channel and breakeven stops | done ([#14], [PR #15]) | | F1 |
| M2 | RSI, SMA and Supertrend exits | done ([#16], [PR #17]) | | F1 |
| B1 | Breakout exits: failed breakout, no progress | done ([#19], [PR #21]) | | F1 |
| F2 | Entry filters on any signal | done ([#22], [PR #23]) | | F1 |
| M1 | Mean-reversion signals | planned | S | |
| O2 | One setup over a watchlist | planned | M | |
| O3 | Monte Carlo of trades | planned | S | |
| F3 | Portfolio backtest | planned | L | |
| R1 | Momentum rotation | planned | L | F3 |
| T2 | Pyramiding | planned | M | F1 |
| O4 | Walk-forward analysis | planned | M/L | O1 |
| O6 | Trade journal and server-side run storage | planned | M | C1 |

Sizes: S is a few rule or signal classes, M touches the engines, API or UI, L is a new engine or page.

**Order:** the table's order. B1 completes the exit rules with the same pattern as T1 and M2. F2 then
improves every strategy family at once, since breakout and trend entries without a trend or market filter
are weak. M1 is small. O2 and O3 show whether a result is robust before the large portfolio engine (F3),
which rotation (R1) needs. Pyramiding (T2), walk-forward analysis (O4) and the trade journal (O6) follow.

## Open items

**M1 · Mean-reversion signals.** New signals for the mean-reversion family: IBS (close in the bottom or
top of the bar's range), N consecutive down or up closes, cumulative RSI(2) over several bars, and
Bollinger %b beyond a level. Signal classes only.

**O2 · One setup over a watchlist.** Run one backtest setup on every ticker of a watchlist, on all cores:
a table of each ticker's metrics (in-sample and out-of-sample), the pooled trade statistics and the spread
of results, so a setting that only works on one ticker shows. CLI, API and a web UI page.

**O3 · Monte Carlo of trades.** Resample a run's R sequence (shuffled and bootstrapped) to show the spread
of maximum drawdown, final return and losing streaks, and the risk of ruin at the run's risk per trade.
On the Backtest page and in Compare.

**F3 · Portfolio backtest.** One setup across a watchlist with shared equity: a cap on open positions and
on total exposure, a priority (score, relative strength) when more signals fire than slots are free, and
portfolio metrics. A new engine path, with a Cerebro reference for parity.

**R1 · Momentum rotation.** Rank a universe by momentum (12-1 month return or IBD-style relative
strength), hold the top N, rebalance weekly or monthly, move to cash or a bond ETF when absolute momentum
is negative, with equal or inverse-volatility weights. Builds on F3.

**T2 · Pyramiding.** Turtle-style adds: another unit each time price moves a set number of ATRs in the
trade's favour, up to a maximum, with the stops of all units moved together. Both engines.

**O4 · Walk-forward analysis.** Rolling windows: sweep on each in-sample window, trade the best setting on
the following out-of-sample window, and stitch the out-of-sample windows into one equity curve. Builds on
the O1 sweep.

**O6 · Trade journal and server-side run storage.** Keep pinned runs and real trades in SQLite on the
server instead of only in the browser, with notes per trade and the backtest that suggested it.

[#4]: https://github.com/devTomaszStoklosa/tradescan/issues/4
[PR #6]: https://github.com/devTomaszStoklosa/tradescan/pull/6
[#7]: https://github.com/devTomaszStoklosa/tradescan/issues/7
[PR #8]: https://github.com/devTomaszStoklosa/tradescan/pull/8
[#10]: https://github.com/devTomaszStoklosa/tradescan/issues/10
[PR #11]: https://github.com/devTomaszStoklosa/tradescan/pull/11
[#12]: https://github.com/devTomaszStoklosa/tradescan/issues/12
[PR #13]: https://github.com/devTomaszStoklosa/tradescan/pull/13
[#14]: https://github.com/devTomaszStoklosa/tradescan/issues/14
[PR #15]: https://github.com/devTomaszStoklosa/tradescan/pull/15
[#16]: https://github.com/devTomaszStoklosa/tradescan/issues/16
[PR #17]: https://github.com/devTomaszStoklosa/tradescan/pull/17
[#19]: https://github.com/devTomaszStoklosa/tradescan/issues/19
[PR #21]: https://github.com/devTomaszStoklosa/tradescan/pull/21
[#22]: https://github.com/devTomaszStoklosa/tradescan/issues/22
[PR #23]: https://github.com/devTomaszStoklosa/tradescan/pull/23
