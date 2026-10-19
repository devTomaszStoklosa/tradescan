from typing import Any

from tests.synthetic import FakeProvider, random_walk
from tradescan.backtest.edge import EdgeSampler, combine_samples, edge_samples
from tradescan.config import Settings
from tradescan.parallel import ProcessRunner, SequentialRunner
from tradescan.services import EdgeRequest, ScanRequest, build_use_cases
from tradescan.signals import default_registry
from tradescan.watchlist import Watchlist

TICKERS = ("AAA", "BBB", "CCC", "DDD")
FRAMES = {name: random_walk(800, seed=seed) for seed, name in enumerate([*TICKERS, "SPY"], start=20)}
UNIVERSE = Watchlist("demo", TICKERS, "SPY")


def _square(value: int) -> int:
    return value * value


def test_runners_keep_input_order():
    items = list(range(12))
    assert SequentialRunner().map(_square, items) == [value * value for value in items]
    assert ProcessRunner(workers=2, min_items=1).map(_square, items) == [value * value for value in items]


def test_process_runner_stays_in_process_for_small_inputs():
    # A lambda cannot be pickled, so this only passes if no worker process is used.
    assert ProcessRunner(workers=4, min_items=10).map(lambda value: value + 1, [1, 2, 3]) == [2, 3, 4]


def test_multi_horizon_samples_match_single_horizon():
    df = FRAMES["AAA"]
    signal = default_registry.create("donchian_breakout")
    together = EdgeSampler((signal,), (5, 10, 20))(df)[0]
    for sample, horizon in zip(together, (5, 10, 20), strict=True):
        alone = edge_samples(df, signal, (horizon,))[0]
        assert combine_samples(signal.name, horizon, [sample]) == combine_samples(signal.name, horizon, [alone])


def _hits(report):
    return [
        (hit.ticker, hit.direction, hit.score.total, tuple(item.signal.name for item in hit.fired), hit.edge)
        for hit in report.hits
    ]


def test_parallel_scan_and_edge_match_sequential():
    sequential = build_use_cases(Settings(), FakeProvider(FRAMES))
    parallel = build_use_cases(Settings(), FakeProvider(FRAMES), runner=ProcessRunner(workers=2, min_items=1))

    # Non-default parameters must reach the worker processes too.
    signal_params = {"donchian_breakout": {"period": 30}, "connors_rsi2_long": {"oversold": 20}}
    settings: dict[str, dict[str, Any]] = {
        "scan": {"fresh_bars": 20, "min_score": -10},
        "trend": {"rs_weights": [0.25, 0.25, 0.25, 0.25]},
    }
    request = ScanRequest(universe=UNIVERSE, settings=settings, signal_params=signal_params)
    assert _hits(parallel.scan.run(request)) == _hits(sequential.scan.run(request))

    edge_request = EdgeRequest(universe=UNIVERSE, signal_params=signal_params)
    assert parallel.edge.run(edge_request).rows == sequential.edge.run(edge_request).rows
