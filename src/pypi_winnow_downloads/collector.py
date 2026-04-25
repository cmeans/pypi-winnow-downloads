from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import badge
from .config import Config, PackageConfig

logger = logging.getLogger(__name__)

# Runner signature: (argv, env) -> CompletedProcess. Both args are always
# passed by run_pypinfo so tests can assert on each independently.
Runner = Callable[[Sequence[str], dict[str, str]], subprocess.CompletedProcess[str]]
Clock = Callable[[], datetime]

_BADGE_LABEL_TEMPLATE = "pip*/uv/poetry/pdm ({days}d)"
_BADGE_FILENAME_TEMPLATE = "downloads-{days}d-non-ci.json"
_HEALTH_FILENAME = "_health.json"

# Installer allowlist for the hero metric. We only count downloads whose
# `details.installer.name` is one of the interactive Python packaging
# tools — the population that approximates "real developers installing
# the package." Mirror traffic (bandersnatch, Nexus, devpi), browser
# fetches, scraper UAs (requests, curl), and unknown installers ("None")
# are excluded. The badge label compresses this set as `pip*/uv/poetry/pdm`
# where `pip*` means the pip-derived family — pip itself plus pipenv and
# pipx (both delegate to pip and inherit its installer telemetry pattern).
#
# Lowercase comparison: pypinfo emits installer_name with the casing the
# BigQuery schema records, which for these tools is lowercase. A
# capitalized variant ("Pip", "PIP") indicates a different category
# (some other UA reusing the name) and is correctly excluded.
_INSTALLER_ALLOWLIST = frozenset({"pip", "uv", "poetry", "pdm", "pipenv", "pipx"})
# pypinfo's own --timeout default is 120s. Pad to 180s so the BigQuery
# call has its own budget plus startup/teardown overhead before our outer
# subprocess.run() abort kicks in. A subprocess hang here would otherwise
# block the systemd timer's next firing.
_DEFAULT_PYPINFO_TIMEOUT_SECONDS = 180

# Console-script filename pypinfo installs as. Windows wheel installs
# emit `.exe`; Unix-flavored installs emit no extension.
_PYPINFO_BIN_NAME = "pypinfo.exe" if sys.platform == "win32" else "pypinfo"


def _resolve_pypinfo_path() -> str:
    """Absolute path to the pypinfo console script in the same venv as
    the running Python interpreter. pypinfo is a runtime dependency so
    its console script is installed alongside this package's; using the
    absolute path skips PATH lookup entirely, which removes a class of
    install-layout-dependent failures (systemd's stripped PATH not
    including the venv bin, container PATH variants, pipx isolated
    venvs, etc.). The function is module-level so tests can monkeypatch
    it to point at a fake binary.
    """
    return str(Path(sys.executable).parent / _PYPINFO_BIN_NAME)


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


def _default_runner(argv: Sequence[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=_DEFAULT_PYPINFO_TIMEOUT_SECONDS,
    )


def _default_clock() -> datetime:
    return datetime.now(UTC)


def run_pypinfo_batch(
    packages: Sequence[str],
    window_days: int,
    *,
    credential_file: Path,
    runner: Runner = _default_runner,
) -> dict[str, int]:
    """Query BigQuery for non-CI, allowlisted-installer downloads of EVERY
    package in *packages* over the same *window_days* window, in a single
    pypinfo invocation. Returns a `{package: count}` dict; packages with
    zero downloads in the window appear in the dict with count=0.

    The batching is the cost lever for hosting many packages: BigQuery
    bills for partition + column scan, NOT for the size of the
    `WHERE file.project IN (...)` list. So one call for N packages costs
    the same as one call for a single package — `bytes_billed` stays
    around 4-5 GB regardless of N. Hosting hundreds of packages on the
    1 TB/month free tier becomes feasible only via this batched path.

    Note: do NOT pass `-a/--auth <path>` on argv. pypinfo (cli.py:130-133)
    short-circuits to a credential-setter path when --auth is present and
    never runs the query. Use GOOGLE_APPLICATION_CREDENTIALS instead.
    """
    if not packages:
        return {}

    # Build the WHERE-IN clause. Package names on PyPI are restricted to
    # [A-Za-z0-9._-] (PEP 508), so they cannot contain quotes or other
    # SQL-meaningful characters; a literal join with double quotes is
    # safe. Belt-and-braces: reject any name containing `"` to fail loud
    # if the input source is ever broadened.
    for p in packages:
        if '"' in p or "\\" in p:
            raise CollectorError(f"package name contains forbidden character: {p!r}")
    project_in = ", ".join(f'"{p}"' for p in packages)
    where_clause = f"file.project IN ({project_in})"

    argv = [
        _resolve_pypinfo_path(),
        "--json",
        "--days",
        str(window_days),
        "--all",
        "--where",
        where_clause,
        # pypinfo's CLI requires a positional [PROJECT] argument before
        # [FIELDS]... — but with --where set, that positional's
        # generated `file.project = "..."` clause is overridden. Pass
        # the first package as a placeholder; --where supersedes.
        packages[0],
        # Pivot by project (so we can split the result per-package),
        # then ci + installer for the existing filters.
        "project",
        "ci",
        "installer",
    ]

    # XDG_DATA_HOME isolation: pypinfo's get_credentials() (db.py:23-26 via
    # cli.py:171) reads a persisted credential path from
    # `platformdirs.user_data_dir('pypinfo')/db.json` and returns it from
    # `creds_file or os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')`
    # (core.py:56) — left-to-right `or` means a persisted path wins and the
    # env var is silently ignored. On any host where `pypinfo -a <path>` has
    # been run manually, that's a foot-gun. Pointing XDG_DATA_HOME at a
    # fresh empty dir per invocation makes pypinfo's TinyDB query return
    # None so the env-var fallback supplies the credential.
    with tempfile.TemporaryDirectory(prefix="pypi-winnow-pypinfo-state-") as state_dir:
        env = {
            **os.environ,
            "GOOGLE_APPLICATION_CREDENTIALS": str(credential_file),
            "XDG_DATA_HOME": state_dir,
        }

        try:
            result = runner(argv, env)
        except subprocess.TimeoutExpired as e:
            raise CollectorError(
                f"pypinfo timed out for batch of {len(packages)} packages after {e.timeout}s"
            ) from e

    if result.returncode != 0:
        raise CollectorError(
            f"pypinfo exited {result.returncode} for batch of {len(packages)} "
            f"packages: {result.stderr.strip()}"
        )
    try:
        payload: Any = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise CollectorError(f"pypinfo produced malformed JSON: {e}") from e

    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise CollectorError("pypinfo output missing 'rows' list")

    counts: dict[str, int] = {p: 0 for p in packages}
    requested = set(packages)
    for row in rows:
        if not isinstance(row, dict):
            raise CollectorError(f"pypinfo row has unexpected shape (not a dict): {row!r}")
        # `project` is required when we pivot by it; missing the column
        # means pypinfo's schema changed under us. Fail loud.
        if "project" not in row:
            raise CollectorError(f"pypinfo row missing 'project' field: {row!r}")
        # Same pattern for installer_name — see the single-package version's
        # comment in earlier collector iterations.
        if "installer_name" not in row:
            raise CollectorError(f"pypinfo row missing 'installer_name' field: {row!r}")
        # pypinfo emits ci as the string "True" / "False" / "None" —
        # BigQuery cell values are passed through str() in
        # parse_query_result. A future pypinfo emitting native bool/None
        # would silently flip this comparison and start counting CI
        # traffic as non-CI; the missing-field guards above catch schema
        # breaks loudly so silent flipping is bounded.
        if row.get("ci") == "True":
            continue
        if row["installer_name"] not in _INSTALLER_ALLOWLIST:
            continue
        project = row["project"]
        if project not in requested:
            # pypinfo returned a row for a package we didn't request —
            # WHERE clause leak, schema break, or bug somewhere. Fail
            # loud rather than silently summing into the wrong bucket.
            raise CollectorError(f"pypinfo returned row for unrequested package: {project!r}")
        count = row.get("download_count", 0)
        if not isinstance(count, int):
            raise CollectorError(
                f"pypinfo row for {project!r} has non-integer download_count: {count!r}"
            )
        counts[project] += count
    return counts


def collect(
    config: Config,
    *,
    clock: Clock = _default_clock,
    runner: Runner = _default_runner,
) -> CollectorResult:
    started = clock()

    # Group packages by window_days. Each group becomes one batched
    # pypinfo invocation — same BigQuery scan cost as a single-package
    # query (partition + columns are constant; WHERE-IN list size is
    # not billed). With everyone on the default 30-day window, this is
    # a single query regardless of how many packages are configured.
    by_window: dict[int, list[PackageConfig]] = {}
    for pkg in config.packages:
        by_window.setdefault(pkg.window_days, []).append(pkg)

    # Per-window batch results. A batch failure (BigQuery error,
    # malformed JSON, schema break) marks every package in that window
    # as failed; per-package failures (currently only the badge write)
    # are isolated below.
    counts_by_pkg: dict[str, int] = {}
    batch_errors: dict[int, str] = {}

    for window, pkgs in by_window.items():
        try:
            batch = run_pypinfo_batch(
                [p.name for p in pkgs],
                window,
                credential_file=config.service.credential_file,
                runner=runner,
            )
        except CollectorError as e:
            logger.error("collector: batch query for window=%dd failed: %s", window, e)
            batch_errors[window] = str(e)
            continue
        counts_by_pkg.update(batch)

    outcomes: list[PackageOutcome] = []
    for pkg in config.packages:
        if pkg.window_days in batch_errors:
            outcomes.append(
                PackageOutcome(
                    package=pkg.name,
                    window_days=pkg.window_days,
                    count=None,
                    error=batch_errors[pkg.window_days],
                )
            )
            continue

        count = counts_by_pkg.get(pkg.name, 0)
        try:
            badge_path = (
                config.service.output_dir
                / pkg.name
                / _BADGE_FILENAME_TEMPLATE.format(days=pkg.window_days)
            )
            payload = badge.build_payload(
                count=count,
                label=_BADGE_LABEL_TEMPLATE.format(days=pkg.window_days),
            )
            badge.write_badge(path=badge_path, payload=payload)
        except OSError as e:
            # Per-package badge-write isolation: a read-only output dir,
            # disk-full, or perms problem for one package must not
            # abort the rest of the run, and must not skip the
            # _health.json write below.
            logger.error("collector: badge write failed for %s: %s", pkg.name, e)
            outcomes.append(
                PackageOutcome(
                    package=pkg.name,
                    window_days=pkg.window_days,
                    count=None,
                    error=f"badge write failed: {e}",
                )
            )
            continue

        logger.info(
            "collector: wrote badge for %s (count=%d, path=%s)",
            pkg.name,
            count,
            badge_path,
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
