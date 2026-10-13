"""FastAPI application factory. Settings and the data provider come from outside, so tests use fakes."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

from tradescan import __version__
from tradescan.api.context import ApiContext
from tradescan.api.routes import backtest, chart, edge, market, meta, scan, signals, watchlists
from tradescan.config import Settings
from tradescan.data.provider import DataProvider
from tradescan.services import EngineFactory, build_scorer, build_use_cases
from tradescan.signals.registry import SignalRegistry, default_registry

ROUTERS = (meta, signals, watchlists, scan, market, edge, backtest, chart)


class SpaStaticFiles(StaticFiles):
    """Serves the built UI and falls back to index.html so client-side routes survive a reload."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as error:
            if error.status_code != 404 or path.startswith("api"):
                raise
            return await super().get_response("index.html", scope)
        if response.status_code == 404 and not path.startswith("api"):
            return await super().get_response("index.html", scope)
        return response


def create_app(
    settings: Settings,
    provider: DataProvider,
    watchlists_dir: Path,
    static_dir: Path | None = None,
    registry: SignalRegistry = default_registry,
    engines: dict[str, EngineFactory] | None = None,
) -> FastAPI:
    context = ApiContext(
        settings=settings,
        use_cases=build_use_cases(settings, provider, registry, engines),
        registry=registry,
        scorer=build_scorer(settings),
        watchlists_dir=watchlists_dir,
    )
    app = FastAPI(title="tradescan", version=__version__, description="Trading signal scanner API")

    @app.exception_handler(ValueError)
    async def value_error(_: Request, error: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @app.exception_handler(ImportError)
    async def import_error(_: Request, error: ImportError) -> JSONResponse:
        return JSONResponse(status_code=501, content={"detail": str(error)})

    for module in ROUTERS:
        app.include_router(module.build_router(context), prefix="/api")

    if static_dir is not None:
        # Windows can map .js to text/plain in the registry, which browsers refuse for module scripts.
        for media_type, extension in (("text/javascript", ".js"), ("text/javascript", ".mjs"), ("text/css", ".css"), ("image/svg+xml", ".svg")):
            mimetypes.add_type(media_type, extension)
        app.mount("/", SpaStaticFiles(directory=static_dir, html=True), name="ui")
    return app
