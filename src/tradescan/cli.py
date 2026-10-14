"""Command line interface: parses arguments, calls the use cases in `services`, renders the reports."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

import pandas as pd
from rich.console import Console

from tradescan.backtest.trade_rules import RuleChoice, default_catalog
from tradescan.config import Settings, load_settings
from tradescan.data.provider import DataProvider
from tradescan.parallel import ProcessRunner
from tradescan.report.console import ConsoleReport
from tradescan.report.export import export_frame
from tradescan.report.tables import (
    SCAN_COLUMNS,
    edge_to_frame,
    hits_to_frame,
    metrics_to_frame,
    signals_to_frame,
    trades_to_frame,
)
from tradescan.services import (
    BacktestRequest,
    EdgeRequest,
    MarketRequest,
    ScanRequest,
    SignalFilter,
    UseCases,
    build_scorer,
    build_use_cases,
    default_engines,
    default_provider,
)
from tradescan.signals import Direction, Family, default_registry
from tradescan.universes import SOURCES, update_universe
from tradescan.watchlist import Watchlist, from_tickers, load_watchlist

Handler = Callable[[argparse.Namespace, Settings, ConsoleReport], int]

ENGINE_CHOICES = [*default_engines(), "both"]
# Exit parameters with their own flags: flag attribute -> (exit rule, parameter).
EXIT_FLAGS = {"target_r": ("target", "target_r"), "max_hold": ("time", "max_hold_bars")}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


# ---------------------------------------------------------------------------
# Wiring helpers


def _provider(settings: Settings, args: argparse.Namespace) -> DataProvider:
    return default_provider(settings, use_cache=not getattr(args, "no_cache", False))


def _use_cases(settings: Settings, args: argparse.Namespace) -> UseCases:
    return build_use_cases(settings, _provider(settings, args), runner=ProcessRunner())


def _universe(args: argparse.Namespace) -> Watchlist:
    if args.tickers:
        return from_tickers(args.tickers)
    return load_watchlist(args.watchlist, Path(args.watchlists_dir))


def _signal_filter(args: argparse.Namespace) -> SignalFilter:
    return SignalFilter(
        names=tuple(_split(args.signals)),
        families=tuple(Family(name) for name in _split(args.family)),
        direction=None if args.direction == "both" else Direction(args.direction),
    )


def _account(args: argparse.Namespace) -> dict[str, float | None]:
    return {"equity": args.equity, "risk_pct": args.risk_pct, "lot_size": args.lot_size}


def _overrides(sections: dict[str, dict[str, float | None]]) -> dict[str, dict[str, float]]:
    """Settings overrides from command-line flags; flags that were not given are left out."""
    result = {}
    for section, values in sections.items():
        given = {key: value for key, value in values.items() if value is not None}
        if given:
            result[section] = given
    return result


def _exits(args: argparse.Namespace) -> tuple[RuleChoice, ...]:
    """The exit rules from `--exits` (default exits when not given, `none` for the stop only) and their flags."""
    if args.exits is None:
        names = list(default_catalog.default_exits)
    else:
        names = [name for name in _split(args.exits) if name != "none"]
    params: dict[str, dict[str, float]] = {}
    for attribute, (rule, name) in EXIT_FLAGS.items():
        value = getattr(args, attribute)
        if value is None:
            continue
        if rule not in names:
            raise ValueError(f"--{attribute.replace('_', '-')} sets the {rule} exit, which --exits leaves out")
        params.setdefault(rule, {})[name] = value
    return tuple(RuleChoice(name, params.get(name, {})) for name in names)


def _split(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _missing(report: ConsoleReport, missing: Sequence[str]) -> None:
    if missing:
        report.warning(f"No data for: {', '.join(missing)}")


def _export(report: ConsoleReport, frame: pd.DataFrame, target: str | None) -> None:
    if target:
        report.note(f"Saved {export_frame(frame, Path(target))}")


def _loading(report: ConsoleReport, count: int, period: str) -> None:
    report.note(f"Loading {count} tickers ({period})...")


# ---------------------------------------------------------------------------
# Commands


def cmd_list_signals(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    signals = default_registry.select()
    report.frame(signals_to_frame(signals, build_scorer(settings)), title=f"{len(signals)} signals")
    return 0


def cmd_scan(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = _universe(args)
    _loading(report, len(universe.tickers) + 1, args.period or settings.data.period)
    result = _use_cases(settings, args).scan.run(
        ScanRequest(
            universe=universe,
            signals=_signal_filter(args),
            settings=_overrides(
                {"account": _account(args), "scan": {"fresh_bars": args.fresh, "min_score": args.min_score}}
            ),
            benchmark=args.benchmark,
            period=args.period,
            interval=args.interval,
        )
    )
    _missing(report, result.missing)
    report.regime(result.regime)
    if result.skipped:
        report.warning(f"Not enough history, skipped: {', '.join(result.skipped)}")
    report.frame(
        hits_to_frame(result.hits[: args.top]),
        title=f"{universe.name}: {len(result.hits)} setups (score >= {result.min_score:g})",
        columns=SCAN_COLUMNS,
        caption=f"signal(bars ago); edge = next-open entry, {result.edge_horizon}-bar outcome of the "
        "most recent signal on this ticker; not investment advice",
    )
    _export(report, hits_to_frame(result.hits), args.export)
    return 0


def cmd_market(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = _universe(args)
    _loading(report, len(universe.tickers) + 1, args.period or settings.data.period)
    result = _use_cases(settings, args).market.run(
        MarketRequest(universe=universe, benchmark=args.benchmark, period=args.period, interval=args.interval)
    )
    _missing(report, result.missing)
    report.regime(result.regime)
    return 0


def cmd_edge(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = _universe(args)
    _loading(report, len(universe.tickers), args.period or settings.backtest.period)
    result = _use_cases(settings, args).edge.run(
        EdgeRequest(
            universe=universe,
            signals=_signal_filter(args),
            horizons=tuple(int(value) for value in _split(args.horizons)),
            min_events=args.min_events,
            period=args.period,
            interval=args.interval,
        )
    )
    _missing(report, result.missing)
    frame = edge_to_frame(result.rows)
    report.frame(
        frame,
        title=f"Signal edge on {universe.name} ({result.tickers} tickers)",
        caption="Returns in the signal's direction from the next open; 'vs base' = minus the average of all bars. "
        "Small N is noise; current watchlists carry survivorship bias.",
    )
    _export(report, frame, args.export)
    return 0


def cmd_backtest(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    _loading(report, 1, args.period or settings.backtest.period)
    engines = tuple(default_engines()) if args.engine == "both" else (args.engine,)
    result = _use_cases(settings, args).backtest.run(
        BacktestRequest(
            ticker=args.ticker,
            signal=args.signal,
            engines=engines,
            settings=_overrides(
                {
                    "account": _account(args),
                    "risk": {"atr_mult": args.atr_mult},
                    "backtest": {"commission_pct": args.commission_pct, "slippage_pct": args.slippage_pct},
                }
            ),
            entry=RuleChoice(args.entry) if args.entry else None,
            exits=_exits(args),
            period=args.period,
            interval=args.interval,
        )
    )
    config, signal, rules = result.config, result.signal, result.rules
    exits = "; ".join(rule.describe() for rule in rules.exits) or "none"
    report.frame(
        metrics_to_frame(result.runs),
        title=f"{result.ticker} {signal.name} ({signal.direction.value}), "
        f"{result.close.index[0].date()} to {result.close.index[-1].date()}",
        caption=f"entry: {rules.entry.describe()}. Stop {config.atr_mult:g} ATR, exits: {exits}. "
        f"Risk {config.risk_pct:g}%/trade, costs {config.commission_pct:g}% + {config.slippage_pct:g}% slippage",
        show_index=True,
    )
    first = result.runs[0].result
    trades = trades_to_frame(first.trades)
    report.frame(trades.tail(args.trades), title=f"Last {args.trades} trades ({first.engine})")
    _export(
        report,
        pd.concat([trades_to_frame(run.result.trades, run.result.engine) for run in result.runs], ignore_index=True),
        args.export,
    )
    return 0


def cmd_update_universes(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    wanted = set(_split(args.only))
    unknown = wanted - {source.name for source in SOURCES}
    if unknown:
        raise ValueError(f"Unknown universe(s): {', '.join(sorted(unknown))}. Use: {', '.join(s.name for s in SOURCES)}")
    failures = 0
    for source in SOURCES:
        if wanted and source.name not in wanted:
            continue
        try:
            result = update_universe(source, Path(args.watchlists_dir))
        except (OSError, ValueError) as error:
            failures += 1
            report.warning(f"{source.title}: not updated, the existing file is kept ({error})")
            continue
        if result.created:
            changes = "created"
        elif result.added or result.removed:
            changes = f"+{len(result.added)} / -{len(result.removed)}"
        else:
            changes = "no changes"
        report.note(f"{source.title}: {len(result.tickers)} tickers -> {result.path} ({changes})")
        if result.added:
            report.note(f"  added: {', '.join(result.added)}")
        if result.removed:
            report.note(f"  removed: {', '.join(result.removed)}")
    return 1 if failures else 0


def cmd_serve(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    try:
        import uvicorn

        from tradescan.api.app import create_app
    except ImportError as error:
        raise ImportError(f"The web server needs the api extra: pip install -e .[api] ({error})") from error

    if args.host not in LOOPBACK_HOSTS:
        report.warning("The API has no authentication. Binding beyond localhost exposes it to your network.")
    static = Path(args.static)
    if not static.is_dir():
        report.warning(f"{static} not found: serving the API only. Build the UI with `npm run build` in frontend/.")
    app = create_app(
        settings=settings,
        provider=_provider(settings, args),
        watchlists_dir=Path(args.watchlists_dir),
        static_dir=static if static.is_dir() else None,
        runner=ProcessRunner(),
    )
    report.note(f"tradescan UI on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


# ---------------------------------------------------------------------------
# Argument parsing


def _add_universe_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-w", "--watchlist", help="watchlist name from the watchlists dir, or a file path")
    group.add_argument("-t", "--tickers", help="comma separated tickers, e.g. AAPL,MSFT,PKO.WA")


def _add_data_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--period", help="yfinance period, e.g. 1y, 5y, max")
    parser.add_argument("--interval", help="yfinance interval (default 1d)")
    parser.add_argument("--no-cache", action="store_true", help="always download fresh data")


def _add_signal_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--signals", help="comma separated signal names (default: all)")
    parser.add_argument("--family", help=f"comma separated families: {', '.join(f.value for f in Family)}")
    parser.add_argument("--direction", choices=["long", "short", "both"], default="both")


def _add_account_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--equity", type=float, help="account size")
    parser.add_argument("--risk-pct", type=float, help="percent of equity risked per trade")
    parser.add_argument("--lot-size", type=float, help="size step, e.g. 0.0001 for crypto")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tradescan",
        description="Trading signal scanner: vectorized pandas signals on yfinance data, optional backtrader check.",
    )
    parser.add_argument("--config", default="config/settings.toml", help="settings file (TOML)")
    parser.add_argument("--watchlists-dir", default="config/watchlists")
    parser.add_argument("-v", "--verbose", action="store_true", help="show data download warnings")
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list-signals", help="show all signals with family, direction and weight")
    listing.set_defaults(handler=cmd_list_signals)

    scan = commands.add_parser("scan", help="find fresh signals, score them and plan the risk")
    _add_universe_args(scan)
    _add_data_args(scan)
    _add_signal_filter_args(scan)
    _add_account_args(scan)
    scan.add_argument("--fresh", type=int, help="signal must have fired within the last N bars")
    scan.add_argument("--min-score", type=float, help="hide setups scoring below this")
    scan.add_argument("--top", type=int, default=25, help="rows to show")
    scan.add_argument("--benchmark", help="benchmark ticker for regime (default from watchlist or settings)")
    scan.add_argument("--export", help="save all hits to .csv or .json")
    scan.set_defaults(handler=cmd_scan)

    market = commands.add_parser("market", help="market regime: benchmark trend and breadth")
    _add_universe_args(market)
    _add_data_args(market)
    market.add_argument("--benchmark")
    market.set_defaults(handler=cmd_market)

    edge = commands.add_parser("edge", help="historical forward returns after each signal")
    _add_universe_args(edge)
    _add_data_args(edge)
    _add_signal_filter_args(edge)
    edge.add_argument("--horizons", default="5,10,20", help="bars after the signal, comma separated")
    edge.add_argument("--min-events", type=int, default=0, help="hide signals with fewer events")
    edge.add_argument("--export", help="save to .csv or .json")
    edge.set_defaults(handler=cmd_edge)

    backtest = commands.add_parser("backtest", help="backtest one signal on one ticker")
    backtest.add_argument("ticker")
    backtest.add_argument("signal", help="signal name, see list-signals")
    backtest.add_argument("--engine", choices=ENGINE_CHOICES, default="vectorized")
    _add_data_args(backtest)
    _add_account_args(backtest)
    backtest.add_argument("--entry", choices=default_catalog.entries.names(), help=f"entry order (default {default_catalog.default_entry})")
    backtest.add_argument(
        "--exits",
        help=f"exit rules on top of the stop, comma separated ({', '.join(default_catalog.exits.names())}); "
        f"'none' keeps only the stop (default {','.join(default_catalog.default_exits)})",
    )
    backtest.add_argument("--atr-mult", type=float, help="stop distance in ATRs")
    backtest.add_argument("--target-r", type=float, help="target as a multiple of the risk (target exit)")
    backtest.add_argument("--max-hold", type=int, help="time exit after N bars (time exit)")
    backtest.add_argument("--commission-pct", type=float)
    backtest.add_argument("--slippage-pct", type=float)
    backtest.add_argument("--trades", type=int, default=10, help="recent trades to show")
    backtest.add_argument("--export", help="save trades to .csv or .json")
    backtest.set_defaults(handler=cmd_backtest)

    universes = commands.add_parser("update-universes", help="refresh the S&P 500 and Nasdaq-100 watchlists from Wikipedia")
    universes.add_argument("--only", help=f"comma separated: {', '.join(source.name for source in SOURCES)}")
    universes.set_defaults(handler=cmd_update_universes)

    serve = commands.add_parser("serve", help="run the web UI and HTTP API (needs the api extra)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--static", default="frontend/dist", help="built frontend to serve")
    serve.add_argument("--no-cache", action="store_true", help="always download fresh data")
    serve.set_defaults(handler=cmd_serve)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.verbose else logging.ERROR, format="%(levelname)s %(message)s")
    if not args.verbose:
        # Missing tickers are already reported once by the scanner; yfinance would log every failure again.
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    report = ConsoleReport(Console())
    try:
        settings = load_settings(Path(args.config))
        handler: Handler = args.handler
        return handler(args, settings, report)
    except (FileNotFoundError, KeyError, ValueError, ImportError) as error:
        message = error.args[0] if error.args else str(error)
        report.warning(f"Error: {message}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
