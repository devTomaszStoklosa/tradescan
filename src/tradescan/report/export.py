"""Write result tables to CSV or JSON, chosen by file extension."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd

_WRITERS: dict[str, Callable[[pd.DataFrame, Path], None]] = {
    ".csv": lambda frame, path: frame.to_csv(path, index=False),
    ".json": lambda frame, path: frame.to_json(path, orient="records", indent=2, date_format="iso"),
}


def export_frame(frame: pd.DataFrame, path: Path) -> Path:
    writer = _WRITERS.get(path.suffix.lower())
    if writer is None:
        raise ValueError(f"Unsupported export format '{path.suffix}'. Use one of: {', '.join(_WRITERS)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    writer(frame, path)
    return path
