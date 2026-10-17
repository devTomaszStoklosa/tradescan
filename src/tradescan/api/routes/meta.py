"""Health check and the defaults and parameter declarations the UI builds its forms from."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan import __version__
from tradescan.api import schemas
from tradescan.api.context import ApiContext
from tradescan.api.mappers import filter_rule_out, priority_rule_out, rule_out, section_out
from tradescan.backtest import sweep
from tradescan.backtest.oos import MIN_PERIOD_BARS
from tradescan.backtest.priority import DEFAULT_PRIORITY
from tradescan.backtest.rotation import DEFAULT_RANKING, Rebalance
from tradescan.backtest.weighting import DEFAULT_WEIGHTING
from tradescan.config import adjustable_sections
from tradescan.services import NOT_SWEEPABLE, SWEEP_SECTIONS
from tradescan.signals.base import Family


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["meta"])
    settings = context.settings

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @router.get("/config", response_model=schemas.ConfigOut)
    def config() -> schemas.ConfigOut:
        rules = context.use_cases.backtest.rules
        return schemas.ConfigOut(
            version=__version__,
            scan_period=settings.data.period,
            backtest_period=settings.backtest.period,
            benchmark=settings.scan.benchmark,
            sections=[section_out(section) for section in adjustable_sections(settings)],
            families=list(Family),
            engines=context.use_cases.backtest.engine_names,
            entry_rules=[rule_out(rule) for rule in rules.entries.classes()],
            exit_rules=[rule_out(rule) for rule in rules.exits.classes()],
            filter_rules=[filter_rule_out(rule) for rule in rules.filters.classes()],
            default_entry=rules.default_entry,
            default_exits=list(rules.default_exits),
            priority_rules=[priority_rule_out(rule) for rule in context.use_cases.portfolio.priorities.classes()],
            default_priority=DEFAULT_PRIORITY,
            ranking_rules=[rule_out(rule) for rule in context.use_cases.rotation.rankings],
            default_ranking=DEFAULT_RANKING,
            weight_rules=[rule_out(rule) for rule in context.use_cases.rotation.weightings.classes()],
            default_weighting=DEFAULT_WEIGHTING,
            rebalances=list(Rebalance),
            sweep=schemas.SweepLimitsOut(
                max_axes=sweep.MAX_AXES,
                min_values=sweep.MIN_VALUES,
                max_values=sweep.MAX_VALUES,
                max_combinations=sweep.MAX_COMBINATIONS,
                sections=list(SWEEP_SECTIONS),
                fixed=sorted(f"{section}.{name}" for section, name in NOT_SWEEPABLE),
                min_period_bars=MIN_PERIOD_BARS,
            ),
        )

    return router
