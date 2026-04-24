from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import badge
from .config import Config

logger = logging.getLogger(__name__)

Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]
Clock = Callable[[], datetime]

_BADGE_LABEL_TEMPLATE = "downloads ({days}d, non-CI)"
_BADGE_FILENAME_TEMPLATE = "downloads-{days}d-non-ci.json"
_HEALTH_FILENAME = "_health.json"


class CollectorError(Exception):
    """Raised when pypinfo invocation or output parsing fails."""


@dataclass(frozen=True)
class PackageOutcome:
    package: str
    window_days: int
    count: int | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class CollectorResult:
    started: datetime
    finished: datetime
    outcomes: tuple[PackageOutcome, ...]

    @property
    def failures(self) -> tuple[PackageOutcome, ...]:
        return tuple(o for o in self.outcomes if not o.ok)


def _default_runner(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(argv), check=False, capture_output=True, text=True)


def _default_clock() -> datetime:
    return datetime.now(UTC)


def run_pypinfo(
    package: str,
    window_days: int,
    *,
    credential_file: Path,
    runner: Runner = _default_runner,
) -> int:
    argv = [
        "pypinfo",
        "--json",
        "--days",
        str(window_days),
        "--all",
        "-a",
        str(credential_file),
        package,
        "ci",
    ]
    result = runner(argv)
    if result.returncode != 0:
        raise CollectorError(
            f"pypinfo exited {result.returncode} for {package!r}: {result.stderr.strip()}"
        )
    try:
        payload: Any = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise CollectorError(f"pypinfo produced malformed JSON for {package!r}: {e}") from e

    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise CollectorError(f"pypinfo output missing 'rows' list for {package!r}")

    total = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("ci") == "True":
            continue
        count = row.get("download_count", 0)
        if not isinstance(count, int):
            raise CollectorError(
                f"pypinfo row for {package!r} has non-integer download_count: {count!r}"
            )
        total += count
    return total


def collect(
    config: Config,
    *,
    clock: Clock = _default_clock,
    runner: Runner = _default_runner,
) -> CollectorResult:
    started = clock()
    outcomes: list[PackageOutcome] = []

    for pkg in config.packages:
        try:
            count = run_pypinfo(
                pkg.name,
                pkg.window_days,
                credential_file=config.service.credential_file,
                runner=runner,
            )
        except CollectorError as e:
            logger.error("collector: %s", e)
            outcomes.append(
                PackageOutcome(
                    package=pkg.name, window_days=pkg.window_days, count=None, error=str(e)
                )
            )
            continue

        badge_path = (
            config.service.output_dir
            / pkg.name
            / _BADGE_FILENAME_TEMPLATE.format(days=pkg.window_days)
        )
        payload = badge.build_payload(
            count=count, label=_BADGE_LABEL_TEMPLATE.format(days=pkg.window_days)
        )
        badge.write_badge(path=badge_path, payload=payload)
        logger.info(
            "collector: wrote badge for %s (count=%d, path=%s)", pkg.name, count, badge_path
        )
        outcomes.append(PackageOutcome(package=pkg.name, window_days=pkg.window_days, count=count))

    finished = clock()
    _write_health(config.service.output_dir, started, finished, outcomes)
    return CollectorResult(started=started, finished=finished, outcomes=tuple(outcomes))


def _write_health(
    output_dir: Path,
    started: datetime,
    finished: datetime,
    outcomes: list[PackageOutcome],
) -> None:
    packages_section: dict[str, dict[str, Any]] = {}
    for o in outcomes:
        if o.ok:
            packages_section[o.package] = {"count": o.count, "window_days": o.window_days}
        else:
            packages_section[o.package] = {"error": o.error, "window_days": o.window_days}

    payload = {
        "started": started.isoformat(),
        "finished": finished.isoformat(),
        "packages": packages_section,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    health_path = output_dir / _HEALTH_FILENAME
    tmp = health_path.parent / (_HEALTH_FILENAME + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, health_path)
