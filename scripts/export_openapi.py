"""Write the API's OpenAPI schema to a file (input for the frontend's generated TypeScript types).

Usage: python scripts/export_openapi.py frontend/openapi.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tradescan.api.app import create_app
from tradescan.config import Settings


class _NoData:
    def history(self, tickers, period, interval):  # pragma: no cover - never called
        return {}


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "frontend/openapi.json")
    schema = create_app(Settings(), _NoData(), Path("config/watchlists")).openapi()
    target.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
