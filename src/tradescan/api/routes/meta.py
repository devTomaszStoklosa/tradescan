"""Health check and the defaults the UI uses to prefill its forms."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan import __version__
from tradescan.api import schemas
from tradescan.api.context import ApiContext
from tradescan.signals.base import Family


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["meta"])
    settings = context.settings

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @router.get("/config", response_model=schemas.ConfigOut)
    def config() -> schemas.ConfigOut:
        return schemas.ConfigOut(
            version=__version__,
            account=schemas.AccountDefaults(
                equity=settings.account.equity,
                risk_pct=settings.account.risk_pct,
                max_position_pct=settings.account.max_position_pct,
                lot_size=settings.account.lot_size,
            ),
            scan=schemas.ScanDefaults(
                fresh_bars=settings.scan.fresh_bars,
                min_score=settings.scan.min_score,
                edge_horizon=settings.scan.edge_horizon,
                benchmark=settings.scan.benchmark,
                period=settings.data.period,
            ),
            backtest=schemas.BacktestDefaults(
                period=settings.backtest.period,
                atr_mult=settings.risk.atr_mult,
                target_r=settings.backtest.target_r,
                max_hold_bars=settings.backtest.max_hold_bars,
                commission_pct=settings.backtest.commission_pct,
                slippage_pct=settings.backtest.slippage_pct,
            ),
            targets_r=list(settings.risk.targets_r),
            families=list(Family),
            engines=context.use_cases.backtest.engine_names,
        )

    return router
