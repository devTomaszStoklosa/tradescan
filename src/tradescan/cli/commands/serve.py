"""`tradescan serve`: the web UI and HTTP API."""

from __future__ import annotations

import argparse
from pathlib import Path

from tradescan.cli import wiring
from tradescan.cli.command import Command
from tradescan.config import Settings
from tradescan.parallel import ProcessRunner
from tradescan.report.console import ConsoleReport
from tradescan.storage.database import Database


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--static", default="frontend/dist", help="built frontend to serve")
    parser.add_argument("--db", default="tradescan.db", help="SQLite file for the pinned runs and the trade journal")
    parser.add_argument("--no-cache", action="store_true", help="always download fresh data")


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def host_header(host: str) -> str:
    """How a browser names the bound address in the Host header: IPv6 literals in brackets."""
    return f"[{host}]" if ":" in host else host


def run(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    try:
        import uvicorn

        from tradescan.api.app import LOCAL_HOSTS, create_app
    except ImportError as error:
        raise ImportError(f"The web server needs the api extra: pip install -e .[api] ({error})") from error

    if args.host not in LOOPBACK_HOSTS:
        report.warning("The API has no authentication. Binding beyond localhost exposes it to your network.")
    static = Path(args.static)
    if not static.is_dir():
        report.warning(f"{static} not found: serving the API only. Build the UI with `npm run build` in frontend/.")
    database = Database(Path(args.db))
    database.migrate()  # a file that is not a tradescan database stops the server before it starts
    app = create_app(
        settings=settings,
        provider=wiring.provider(settings, args),
        watchlists_dir=Path(args.watchlists_dir),
        static_dir=static if static.is_dir() else None,
        runner=ProcessRunner(),
        database=database,
        allowed_hosts=(*LOCAL_HOSTS, host_header(args.host)),
    )
    report.note(f"tradescan UI on http://{args.host}:{args.port}, pinned runs and the journal in {database.location}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


COMMAND = Command(
    name="serve", help="run the web UI and HTTP API (needs the api extra)", add_arguments=add_arguments, run=run
)
