"""Command line interface and composition root: the only place that wires concrete classes together."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

import pandas as pd
from rich.console import Console

from tradescan.backtest.base import BacktestConfig, BacktestEngine
from tradescan.backtest.edge import EdgeAnalyzer
from tradescan.backtest.metrics import compute_metrics
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.config import Settings, load_settings
from tradescan.context import ContextBuilder
from tradescan.data.cache import CachedProvider
from tradescan.data.provider import DataProvider
from tradescan.data.yfinance_provider import YFinanceProvider
from tradescan.regime import MarketRegimeAnalyzer
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
from tradescan.risk import RiskPlanner
from tradescan.scanner import Scanner, filter_hits
from tradescan.scoring import Scorer
from tradescan.signals import Direction, Family, Signal, default_registry
from tradescan.watchlist import Watchlist, from_tickers, load_watchlist

Handler = Callable[[argparse.Namespace, Settings, ConsoleReport], int]


def _load_cerebro_engine() -> BacktestEngine:
    from tradescan.backtest.cerebro import CerebroEngine

    return CerebroEngine()


ENGINES: dict[str, Callable[[], BacktestEngine]] = {
    "vectorized": VectorizedEngine,
    "cerebro": _load_cerebro_engine,
}


# ---------------------------------------------------------------------------
# Wiring helpers


def _provider(settings: Settings, args: argparse.Namespace) -> DataProvider:
    provider = YFinanceProvider()
    if args.no_cache:
        return provider
    return CachedProvider(provider, Path(settings.data.cache_dir), settings.data.cache_ttl_hours * 3600.0)


def _universe(args: argparse.Namespace) -> Watchlist:
    if args.tickers:
        return from_tickers(args.tickers)
    return load_watchlist(args.watchlist, Path(args.watchlists_dir))


def _fetch(
    args: argparse.Namespace, settings: Settings, tickers: Sequence[str], period: str, report: ConsoleReport
) -> dict[str, pd.DataFrame]:
    unique = list(dict.fromkeys(tickers))
    report.note(f"Loading {len(unique)} tickers ({period}, {args.interval or settings.data.interval})...")
    return _provider(settings, args).history(unique, period, args.interval or settings.data.interval)


def _scorer(settings: Settings) -> Scorer:
    scoring = settings.scoring
    return Scorer(
        family_weights=scoring.family_weights,
        signal_weights=scoring.signal_weights,
        trend_bonus=scoring.trend_bonus,
        weekly_bonus=scoring.weekly_bonus,
        rs_bonus=scoring.rs_bonus,
        rs_strong_pct=scoring.rs_strong_pct,
    )


def _directions(value: str) -> set[Direction] | None:
    return None if value == "both" else {Direction(value)}


def _signals(args: argparse.Namespace) -> list[Signal]:
    names = _split(args.signals)
    families = {Family(name) for name in _split(args.family)} or None
    return default_registry.select(names=names or None, families=families, directions=_directions(args.direction))


def _split(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _missing(report: ConsoleReport, requested: Sequence[str], frames: dict[str, pd.DataFrame]) -> None:
    missing = [ticker for ticker in requested if ticker not in frames]
    if missing:
        report.warning(f"No data for: {', '.join(missing)}")


def _export(report: ConsoleReport, frame: pd.DataFrame, target: str | None) -> None:
    if target:
        report.note(f"Saved {export_frame(frame, Path(target))}")


# ---------------------------------------------------------------------------
# Commands


def cmd_list_signals(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    signals = default_registry.select()
    report.frame(signals_to_frame(signals, _scorer(settings)), title=f"{len(signals)} signals")
    return 0


def cmd_scan(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = _universe(args)
    benchmark = (args.benchmark or universe.benchmark or settings.scan.benchmark).upper()
    frames = _fetch(args, settings, [*universe.tickers, benchmark], args.period or settings.data.period, report)
    _missing(report, universe.tickers, frames)
    universe_frames = {ticker: frames[ticker] for ticker in universe.tickers if ticker in frames}
    report.regime(MarketRegimeAnalyzer().analyze(benchmark, frames.get(benchmark), universe_frames))

    account = settings.account
    scanner = Scanner(
        signals=_signals(args),
        context_builder=ContextBuilder(atr_period=settings.risk.atr_period),
        scorer=_scorer(settings),
        risk_planner=RiskPlanner(
            equity=args.equity or account.equity,
            risk_pct=args.risk_pct or account.risk_pct,
            max_position_pct=account.max_position_pct,
            atr_mult=settings.risk.atr_mult,
            targets_r=settings.risk.targets_r,
            lot_size=args.lot_size or account.lot_size,
        ),
        edge_analyzer=EdgeAnalyzer(settings.scan.edge_horizon),
        fresh_bars=args.fresh or settings.scan.fresh_bars,
        min_bars=settings.scan.min_bars,
    )
    result = scanner.scan(universe_frames)
    if result.skipped:
        report.warning(f"Not enough history, skipped: {', '.join(result.skipped)}")

    min_score = settings.scan.min_score if args.min_score is None else args.min_score
    hits = filter_hits(result.hits, min_score=min_score, directions=_directions(args.direction))
    report.frame(
        hits_to_frame(hits[: args.top]),
        title=f"{universe.name}: {len(hits)} setups (score >= {min_score:g})",
        columns=SCAN_COLUMNS,
        caption=f"signal(bars ago); edge = next-open entry, {settings.scan.edge_horizon}-bar outcome of the "
        "most recent signal on this ticker; not investment advice",
    )
    _export(report, hits_to_frame(hits), args.export)
    return 0


def cmd_market(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = _universe(args)
    benchmark = (args.benchmark or universe.benchmark or settings.scan.benchmark).upper()
    frames = _fetch(args, settings, [*universe.tickers, benchmark], args.period or settings.data.period, report)
    _missing(report, universe.tickers, frames)
    universe_frames = {ticker: frames[ticker] for ticker in universe.tickers if ticker in frames}
    report.regime(MarketRegimeAnalyzer().analyze(benchmark, frames.get(benchmark), universe_frames))
    return 0


def cmd_edge(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = _universe(args)
    frames = _fetch(args, settings, universe.tickers, args.period or settings.backtest.period, report)
    _missing(report, universe.tickers, frames)
    horizons = [int(value) for value in _split(args.horizons)]
    if not horizons or min(horizons) < 1:
        raise ValueError("--horizons needs positive integers, e.g. 5,10,20")

    analyzers = [EdgeAnalyzer(horizon) for horizon in horizons]
    histories = list(frames.values())
    rows = [(signal, [analyzer.analyze(histories, signal) for analyzer in analyzers]) for signal in _signals(args)]
    frame = edge_to_frame(rows)
    sort_horizon = horizons[len(horizons) // 2]
    if not frame.empty:
        frame = frame[frame[f"N {horizons[0]}d"] >= args.min_events]
        frame = frame.sort_values(f"vs base% {sort_horizon}d", ascending=False, na_position="last")
    report.frame(
        frame,
        title=f"Signal edge on {universe.name} ({len(frames)} tickers)",
        caption="Returns in the signal's direction from the next open; 'vs base' = minus the average of all bars. "
        "Small N is noise; current watchlists carry survivorship bias.",
    )
    _export(report, frame, args.export)
    return 0


def cmd_backtest(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    ticker = args.ticker.upper()
    signal = default_registry.create(args.signal)
    frames = _fetch(args, settings, [ticker], args.period or settings.backtest.period, report)
    if ticker not in frames:
        raise ValueError(f"No data for {ticker}")
    df = frames[ticker]

    account, backtest = settings.account, settings.backtest
    config = BacktestConfig(
        initial_equity=args.equity or account.equity,
        risk_pct=args.risk_pct or account.risk_pct,
        max_position_pct=account.max_position_pct,
        lot_size=args.lot_size or account.lot_size,
        atr_period=settings.risk.atr_period,
        atr_mult=args.atr_mult or settings.risk.atr_mult,
        target_r=args.target_r or backtest.target_r,
        max_hold_bars=args.max_hold or backtest.max_hold_bars,
        commission_pct=backtest.commission_pct if args.commission_pct is None else args.commission_pct,
        slippage_pct=backtest.slippage_pct if args.slippage_pct is None else args.slippage_pct,
        bars_per_year=backtest.bars_per_year,
    )
    engine_names = list(ENGINES) if args.engine == "both" else [args.engine]
    results = []
    for name in engine_names:
        result = ENGINES[name]().run(ticker, df, signal, config)
        results.append((result, compute_metrics(result.equity, result.trades, df["close"], config.bars_per_year)))

    first = df.index[0].date()
    last = df.index[-1].date()
    report.frame(
        metrics_to_frame(results),
        title=f"{ticker} {signal.name} ({signal.direction.value}), {first} to {last}",
        caption=f"stop {config.atr_mult:g} ATR, target {config.target_r:g}R, time exit {config.max_hold_bars} bars, "
        f"risk {config.risk_pct:g}%/trade, costs {config.commission_pct:g}% + {config.slippage_pct:g}% slippage",
        show_index=True,
    )
    trades = trades_to_frame(results[0][0].trades)
    report.frame(trades.tail(args.trades), title=f"Last {args.trades} trades ({results[0][0].engine})")
    _export(report, pd.concat([trades_to_frame(r.trades, r.engine) for r, _ in results], ignore_index=True), args.export)
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
    backtest.add_argument("--engine", choices=[*ENGINES, "both"], default="vectorized")
    _add_data_args(backtest)
    _add_account_args(backtest)
    backtest.add_argument("--atr-mult", type=float, help="stop distance in ATRs")
    backtest.add_argument("--target-r", type=float, help="target as a multiple of the risk")
    backtest.add_argument("--max-hold", type=int, help="time exit after N bars")
    backtest.add_argument("--commission-pct", type=float)
    backtest.add_argument("--slippage-pct", type=float)
    backtest.add_argument("--trades", type=int, default=10, help="recent trades to show")
    backtest.add_argument("--export", help="save trades to .csv or .json")
    backtest.set_defaults(handler=cmd_backtest)
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
