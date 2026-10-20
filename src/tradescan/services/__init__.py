"""Use cases shared by the CLI and the HTTP API, one module per use case.

Each use case takes a request dataclass and returns a report dataclass; neither knows about
argparse, HTTP or rendering. `composition.build_use_cases` wires them from settings and a data provider.

Requests carry per-run overrides: `settings` ({section: {parameter: value}}) and signal parameters
({signal name: {parameter: value}}); a backtest also names its entry filters, entry rule and exit rules
with their parameters. All are validated against the declared ranges, and the configured settings are never modified.
A sweep reruns one backtest setup over a grid of one or two of those parameters, a walk-forward re-tunes it
on rolling windows and trades each pick on the window after it, a watchlist backtest
runs it on every ticker of a watchlist, and a portfolio backtest on every ticker of a watchlist with one
shared equity. A rotation holds the strongest tickers of a watchlist, rebalanced on a calendar.
"""
