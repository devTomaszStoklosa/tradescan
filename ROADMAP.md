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
| M1 | Mean-reversion signals | done ([#24], [PR #25]) | | |
| O2 | One setup over a watchlist | done ([#26], [PR #27]) | | |
| O3 | Monte Carlo of trades | done ([#28], [PR #29]) | | |
| F3 | Portfolio backtest | done ([#30], [PR #31]) | | |
| R1 | Momentum rotation | done ([#41], [PR #42]) | | F3 |
| T2 | Pyramiding | done ([#48], [PR #49]) | | F1 |
| O4 | Walk-forward analysis | planned | M/L | O1 |
| O6 | Trade journal and server-side run storage | planned | M | C1 |

Sizes: S is a few rule or signal classes, M touches the engines, API or UI, L is a new engine or page.

**Order:** the table's order. B1 completes the exit rules with the same pattern as T1 and M2. F2 then
improves every strategy family at once, since breakout and trend entries without a trend or market filter
are weak. M1 is small. O2 and O3 show whether a result is robust before the large portfolio engine (F3),
which rotation (R1) needs. Pyramiding (T2), walk-forward analysis (O4) and the trade journal (O6) follow.

## Open items

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
[#24]: https://github.com/devTomaszStoklosa/tradescan/issues/24
[PR #25]: https://github.com/devTomaszStoklosa/tradescan/pull/25
[#26]: https://github.com/devTomaszStoklosa/tradescan/issues/26
[PR #27]: https://github.com/devTomaszStoklosa/tradescan/pull/27
[#28]: https://github.com/devTomaszStoklosa/tradescan/issues/28
[PR #29]: https://github.com/devTomaszStoklosa/tradescan/pull/29
[#30]: https://github.com/devTomaszStoklosa/tradescan/issues/30
[PR #31]: https://github.com/devTomaszStoklosa/tradescan/pull/31
[#41]: https://github.com/devTomaszStoklosa/tradescan/issues/41
[PR #42]: https://github.com/devTomaszStoklosa/tradescan/pull/42
[#48]: https://github.com/devTomaszStoklosa/tradescan/issues/48
[PR #49]: https://github.com/devTomaszStoklosa/tradescan/pull/49
