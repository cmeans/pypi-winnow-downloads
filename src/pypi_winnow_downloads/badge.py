from __future__ import annotations

import json
import os
from pathlib import Path

_LOW_COUNT_THRESHOLD = 10
_DEFAULT_COLOR = "blue"
_LOW_COUNT_COLOR = "lightgrey"


def format_count(n: int) -> str:
    if n < 0:
        raise ValueError(f"count must be non-negative, got {n}")
    if n < 1000:
        return str(n)
    # Round first, then decide the suffix — otherwise 999_999 would render
    # as "1000.0k" because .1f rounds 999.999 up to 1000.0.
    k_value = round(n / 1000, 1)
    if k_value < 1000:
        return _format_with_suffix(k_value, "k")
    return _format_with_suffix(round(n / 1_000_000, 1), "M")


def _format_with_suffix(value: float, suffix: str) -> str:
    if value == int(value):
        return f"{int(value)}{suffix}"
    return f"{value:.1f}{suffix}"


def build_payload(*, count: int, label: str) -> dict:
    color = _LOW_COUNT_COLOR if count < _LOW_COUNT_THRESHOLD else _DEFAULT_COLOR
    return {
        "schemaVersion": 1,
        "label": label,
        "message": format_count(count),
        "color": color,
    }


def write_badge(*, path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(tmp, path)
