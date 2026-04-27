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
    health_write_error: str | None = None

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


def run_pypinfo(
    package: str,
    window_days: int,
    *,
    credential_file: Path,
    runner: Runner = _default_runner,
) -> int:
    # Note: do NOT pass `-a/--auth <path>` on argv. pypinfo (cli.py:130-133)
    # short-circuits to a credential-setter path when --auth is present and
    # never runs the query. Use GOOGLE_APPLICATION_CREDENTIALS instead, which
    # pypinfo's core.py reads via os.environ.get on the no-flag path.
    argv = [
        _resolve_pypinfo_path(),
        "--json",
        "--days",
        str(window_days),
        "--all",
        package,
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
            raise CollectorError(f"pypinfo timed out for {package!r} after {e.timeout}s") from e

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
            raise CollectorError(
                f"pypinfo row for {package!r} has unexpected shape (not a dict): {row!r}"
            )
        # pypinfo emits ci as the *string* "True" / "False" / "None" — BigQuery
        # cell values are passed through str() in pypinfo's parse_query_result.
        # If a future pypinfo version emits a native bool/None instead, this
        # comparison would silently flip and start counting CI traffic as
        # non-CI; the non-dict-row guard above catches schema breaks loudly.
        if row.get("ci") == "True":
            continue
        # installer_name is required when we pivot by `installer`; missing
        # the column means pypinfo's schema changed under us and we should
        # fail loudly rather than silently undercount.
        if "installer_name" not in row:
            raise CollectorError(
                f"pypinfo row for {package!r} missing 'installer_name' field: {row!r}"
            )
        if row["installer_name"] not in _INSTALLER_ALLOWLIST:
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
    _check_staleness(
        output_dir=config.service.output_dir,
        threshold_days=config.service.stale_threshold_days,
        now=started,
    )
    outcomes: list[PackageOutcome] = []

    for pkg in config.packages:
        outcome = _collect_one(pkg, config, runner)
        outcomes.append(outcome)

    finished = clock()
    health_write_error: str | None = None
    try:
        _write_health(config.service.output_dir, started, finished, outcomes)
    except OSError as e:
        # Mirror the per-package isolation contract one level up: a write
        # failure here (disk full, output dir not writable, cross-device
        # atomic-replace, etc.) must not propagate as a raw traceback that
        # bypasses the structured exit path in __main__. Surface via
        # CollectorResult.health_write_error so the caller can fold it
        # into the exit message.
        logger.error("collector: failed to write _health.json: %s", e)
        health_write_error = str(e)
    return CollectorResult(
        started=started,
        finished=finished,
        outcomes=tuple(outcomes),
        health_write_error=health_write_error,
    )


def _collect_one(
    pkg: PackageConfig,
    config: Config,
    runner: Runner,
) -> PackageOutcome:
    try:
        count = run_pypinfo(
            pkg.name,
            pkg.window_days,
            credential_file=config.service.credential_file,
            runner=runner,
        )
        badge_path = (
            config.service.output_dir
            / pkg.name
            / _BADGE_FILENAME_TEMPLATE.format(days=pkg.window_days)
        )
        payload = badge.build_payload(
            count=count, label=_BADGE_LABEL_TEMPLATE.format(days=pkg.window_days)
        )
        badge.write_badge(path=badge_path, payload=payload)
    except (CollectorError, OSError) as e:
        # Per-package isolation: a single package's BigQuery failure or disk
        # write failure must not abort the whole run, and must not skip the
        # _health.json write. Operators rely on _health.json as the single
        # diagnostic surface for the v1 staleness mechanism.
        logger.error("collector: %s", e)
        return PackageOutcome(
            package=pkg.name, window_days=pkg.window_days, count=None, error=str(e)
        )

    logger.info("collector: wrote badge for %s (count=%d, path=%s)", pkg.name, count, badge_path)
    return PackageOutcome(package=pkg.name, window_days=pkg.window_days, count=count)


def _check_staleness(
    output_dir: Path,
    threshold_days: int,
    now: datetime,
) -> None:
    """Read the previous run's _health.json and emit a logger.warning if its
    `finished` timestamp is older than `threshold_days` ago. Log-only — does
    NOT mutate badge JSON. Per `config.example.yaml`'s documented contract.

    No-op (silent) when:
    - The previous _health.json doesn't exist (first run, fresh deploy)
    - The file exists but is unreadable / unparseable / missing the
      `finished` field (logged at DEBUG so operators can grep, but the
      collector run itself proceeds)
    - The previous `finished` is in the future relative to `now` (clock
      skew, manually-edited file) — silently skip
    """
    health_path = output_dir / _HEALTH_FILENAME
    try:
        raw = health_path.read_text()
    except FileNotFoundError:
        return
    except OSError as e:
        logger.debug("collector: cannot read previous _health.json for staleness check: %s", e)
        return

    try:
        payload = json.loads(raw)
        finished_raw = payload["finished"]
        previous_finished = datetime.fromisoformat(finished_raw)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.debug("collector: previous _health.json unparseable for staleness check: %s", e)
        return

    age = now - previous_finished
    if age.total_seconds() < 0:
        return  # clock skew or hand-edited file
    age_days = age.total_seconds() / 86400.0
    if age_days > threshold_days:
        logger.warning(
            "collector: previous successful run is %.1f days old (threshold: %d days); "
            "previous finished: %s",
            age_days,
            threshold_days,
            previous_finished.isoformat(),
        )


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
