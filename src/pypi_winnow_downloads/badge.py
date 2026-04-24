# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import os
from pathlib import Path

_LOW_COUNT_THRESHOLD = 10
_DEFAULT_COLOR = "blue"
_LOW_COUNT_COLOR = "lightgrey"


def format_count(n: int) -> str:
    if n >= 1_000_000:
        value, suffix = n / 1_000_000, "M"
    elif n >= 1000:
        value, suffix = n / 1000, "k"
    else:
        return str(n)

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
