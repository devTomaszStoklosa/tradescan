import pickle
from dataclasses import asdict

import pytest

from tests.synthetic import FakeProvider, random_walk
from tradescan.backtest.priority import MomentumPriority
from tradescan.backtest.rotation import Rebalance
from tradescan.backtest.rotation_sweep import RotationSweepAxis, RotationSweepCase, RotationSweepJob
from tradescan.backtest.rotation_sweep import RotationSweepTarget as Target
from tradescan.backtest.trade_rules import RuleChoice
from tradescan.config import Settings
from tradescan.services.composition import build_use_cases
from tradescan.services.rotation import RotationRequest
from tradescan.services.rotation_sweep import RotationSweepRequest
from tradescan.watchlist import Watchlist

UNIVERSE = Watchlist("demo", ("T0", "T1", "T2", "T3", "NODATA"), benchmark="SPY")


@pytest.fixture(scope="module")
def market():
    walks = {f"T{i}": random_walk(1500, seed=i) for i in range(4)}
    return {**walks, "SPY": random_walk(1500, seed=50), "TLT": random_walk(1500, seed=51, volatility=0.005)}


def _use_cases(frames):
    return build_use_cases(Settings(), FakeProvider(frames))


def _setup(**changes):
    request = {
        "universe": UNIVERSE,
        "rebalance": Rebalance.WEEKLY,
        "safe_asset": "TLT",
        "settings": {"rotation": {"holdings": 2, "absolute_lookback": 63}},
    }
    return RotationRequest(**{**request, **changes})


def _same(left, right):
    """Whether two rotation periods have the same metrics and stats; NaN equals NaN."""
    for part in ("metrics", "stats"):
        assert asdict(getattr(left, part)) == pytest.approx(asdict(getattr(right, part)), nan_ok=True)


def _sweep(frames, *axes, setup=None):
    return _use_cases(frames).rotation_sweep.run(RotationSweepRequest(setup or _setup(), tuple(axes)))


def test_a_grid_runs_every_combination_at_the_setups_split(market):
    report = _sweep(
        market,
        RotationSweepAxis(Target.SETTINGS, "holdings", (1, 2, 3), owner="rotation"),
        RotationSweepAxis(Target.RANKING, "lookback", (126.0, 252.0)),
    )
    assert [cell.values for cell in report.cells] == [
        (1, 126),
        (1, 252),
        (2, 126),
        (2, 252),
        (3, 126),
        (3, 252),
    ]
    assert all(cell.periods is not None and cell.error is None for cell in report.cells)
    holdings, lookback = report.parameters
    assert (holdings.axis.key, holdings.spec.label, holdings.spec.default) == (
        "settings.rotation.holdings",
        "Holdings",
        2,
    )
    assert (lookback.axis.key, lookback.spec.default) == ("ranking.lookback", 252)
    assert report.base.ranking == MomentumPriority()
    assert report.missing == ["NODATA"]
    # More holdings spread the equity over more tickers, so the combinations differ.
    returns = {
        cell.values: cell.periods.out_of_sample.metrics.total_return_pct for cell in report.cells if cell.periods
    }
    assert len(set(returns.values())) > 1

    rotation = _use_cases(market).rotation.run(_setup())
    assert report.split == rotation.split
    assert report.dates.equals(rotation.dates)
    (run,) = rotation.runs
    setup_cell = next(cell for cell in report.cells if cell.values == (2, 252))
    assert setup_cell.periods is not None
    assert run.in_sample is not None
    assert run.out_of_sample is not None
    _same(setup_cell.periods.in_sample, run.in_sample)
    _same(setup_cell.periods.out_of_sample, run.out_of_sample)


def test_weighting_and_cost_parameters_reach_every_combination(market):
    setup = _setup(weighting=RuleChoice("inverse_volatility"))
    report = _sweep(
        market,
        RotationSweepAxis(Target.WEIGHTING, "lookback", (20, 63)),
        RotationSweepAxis(Target.SETTINGS, "commission_pct", (0.0, 1.0), owner="backtest"),
        setup=setup,
    )
    assert report.parameters[0].spec.default == 63
    periods = {cell.values: cell.periods.out_of_sample for cell in report.cells if cell.periods}
    assert periods[(20, 0.0)].stats.commissions == 0.0
    assert periods[(20, 1.0)].stats.commissions > 0.0
    assert periods[(20, 0.0)].metrics.total_return_pct != periods[(63, 0.0)].metrics.total_return_pct


def test_a_combination_that_breaks_a_rule_between_parameters_is_an_error_cell(market):
    report = _sweep(market, RotationSweepAxis(Target.RANKING, "lookback", (21, 252)))
    broken, fine = report.cells
    assert broken.periods is None
    assert broken.error is not None
    assert "skip (21) must be below the lookback (21)" in broken.error
    assert fine.periods is not None


def test_a_combination_whose_lookback_outlasts_the_in_sample_history_is_an_error_cell(market):
    short = {ticker: frame.iloc[:600] for ticker, frame in market.items()}
    report = _sweep(
        short,
        RotationSweepAxis(Target.SETTINGS, "absolute_lookback", (63, 1000), owner="rotation"),
        setup=_setup(settings={"rotation": {"holdings": 2, "absolute_lookback": 63}}),
    )
    fine, empty = report.cells
    assert fine.periods is not None
    assert empty.periods is None
    assert empty.error == "No in-sample rebalance had a ticker to pick: a lookback is longer than the in-sample history"


@pytest.mark.parametrize(
    ("axis", "message"),
    [
        (RotationSweepAxis(Target.SETTINGS, "oos_pct", (20, 30), owner="backtest"), "sets the out-of-sample split"),
        (
            RotationSweepAxis(Target.SETTINGS, "equity", (1000, 2000), owner="account"),
            "rotation sweeps can change the settings in rotation, backtest",
        ),
        (RotationSweepAxis(Target.RANKING, "lookback", (126, 252), owner="momentum"), "takes no owner"),
        (RotationSweepAxis(Target.RANKING, "nope", (1, 2)), "momentum: unknown or fixed parameter 'nope'"),
        (RotationSweepAxis(Target.WEIGHTING, "lookback", (20, 63)), "equal: unknown or fixed parameter 'lookback'"),
        (RotationSweepAxis(Target.SETTINGS, "holdings", (0, 1), owner="rotation"), "between 1 and 50"),
        (RotationSweepAxis(Target.SETTINGS, "holdings", (1.5, 2), owner="rotation"), "whole number"),
    ],
)
def test_axes_the_rotation_cannot_sweep_are_refused(market, axis, message):
    with pytest.raises(ValueError, match=message):
        _sweep(market, axis)


def test_list_parameters_and_bad_grids_are_refused(market):
    with pytest.raises(ValueError, match=r"relative_strength\.periods is not a single number"):
        _sweep(
            market,
            RotationSweepAxis(Target.RANKING, "periods", (63, 126)),
            setup=_setup(ranking=RuleChoice("relative_strength")),
        )
    holdings = RotationSweepAxis(Target.SETTINGS, "holdings", (1, 2), owner="rotation")
    with pytest.raises(ValueError, match="can be swept only once"):
        _sweep(market, holdings, holdings)
    with pytest.raises(ValueError, match="needs 2 to 50 values"):
        _sweep(market, RotationSweepAxis(Target.SETTINGS, "holdings", (1,), owner="rotation"))


def test_a_rotation_too_short_to_split_or_to_pick_is_refused(market):
    short = {ticker: frame.iloc[:350] for ticker, frame in market.items()}
    axis = RotationSweepAxis(Target.SETTINGS, "holdings", (1, 2), owner="rotation")
    with pytest.raises(ValueError, match="too few to split at 30%"):
        _sweep(short, axis)
    shorter = {ticker: frame.iloc[:200] for ticker, frame in market.items()}
    with pytest.raises(ValueError, match="shorter than the ranking"):
        _sweep(shorter, axis)


def test_the_job_pickles_for_worker_processes(market):
    frames = {ticker: market[ticker] for ticker in ("T0", "T1")}
    report = _sweep(market, RotationSweepAxis(Target.SETTINGS, "holdings", (1, 2), owner="rotation"))
    base = report.base
    job = RotationSweepJob(frames, market["TLT"], market["SPY"]["close"], report.split.out_of_sample[0])
    case = RotationSweepCase(base.config, base.rotation, base.ranking, base.weighting)
    copied, direct = pickle.loads(pickle.dumps(job))(case), job(case)
    _same(copied.in_sample, direct.in_sample)
    _same(copied.out_of_sample, direct.out_of_sample)
