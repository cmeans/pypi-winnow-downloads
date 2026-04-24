import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pypi_winnow_downloads.collector import CollectorError, collect, run_pypinfo
from pypi_winnow_downloads.config import Config, PackageConfig, ServiceConfig


def _ok_result(argv: list[str], stdout: str = '{"rows": []}') -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")


def test_run_pypinfo_invokes_pypinfo_with_expected_argv(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def fake_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        captured.append(list(argv))
        return _ok_result(argv)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)

    assert len(captured) == 1
    argv = captured[0]
    assert argv[0] == "pypinfo"
    assert "--json" in argv
    assert argv[argv.index("--days") + 1] == "30"
    assert "--all" in argv
    assert argv[argv.index("-a") + 1] == str(creds)
    assert "mypkg" in argv
    # The ci field must be the pivot, and must appear AFTER the package name
    # per pypinfo's positional argument order (PROJECT then FIELDS).
    assert argv.index("mypkg") < argv.index("ci")


def test_run_pypinfo_sums_non_ci_rows_and_excludes_ci_true(tmp_path: Path) -> None:
    # pypinfo emits rows where the ci cell is the string "True", "False", or
    # "None" (BigQuery passes values through str()). Only "True" rows should
    # be excluded from the non-CI download count.
    stdout = json.dumps(
        {
            "rows": [
                {"ci": "True", "download_count": 900},
                {"ci": "False", "download_count": 70},
                {"ci": "None", "download_count": 25},
            ],
            "query": {},
        }
    )

    def fake_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout=stdout)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    count = run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)

    assert count == 95  # 70 + 25, excluding the 900 CI downloads


def test_run_pypinfo_returns_zero_when_rows_empty(tmp_path: Path) -> None:
    # pypinfo returns an empty rows list when the package has no downloads
    # in the window (or doesn't exist on PyPI).
    def fake_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout='{"rows": [], "query": {}}')

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    count = run_pypinfo("newpkg", 30, credential_file=creds, runner=fake_runner)

    assert count == 0


def test_run_pypinfo_raises_on_nonzero_exit(tmp_path: Path) -> None:
    def fake_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="auth failed")

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="auth failed"):
        run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)


def test_run_pypinfo_raises_on_malformed_json(tmp_path: Path) -> None:
    def fake_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout="not json at all")

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="malformed JSON"):
        run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)


def test_run_pypinfo_raises_when_rows_key_missing(tmp_path: Path) -> None:
    # pypinfo always emits a `rows` key; its absence means the response is
    # from an unexpected source (old pypinfo, upstream format change, etc.).
    def fake_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout='{"query": {}}')

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="rows"):
        run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)


# --- collect() orchestration ---


def _make_config(tmp_path: Path, packages: list[PackageConfig]) -> Config:
    return Config(
        service=ServiceConfig(
            output_dir=tmp_path / "out",
            credential_file=tmp_path / "creds.json",
            stale_threshold_days=3,
        ),
        packages=tuple(packages),
    )


def _fake_runner_for(counts_by_package: dict[str, int]):
    """Return a runner that emits pypinfo-shaped JSON with the given non-CI total
    for each package. The package name is read from argv (positional just before 'ci').
    """

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        ci_idx = argv.index("ci")
        pkg = argv[ci_idx - 1]
        non_ci_count = counts_by_package.get(pkg, 0)
        stdout = json.dumps(
            {
                "rows": [
                    {"ci": "True", "download_count": 10_000},
                    {"ci": "False", "download_count": non_ci_count},
                ],
                "query": {},
            }
        )
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    return runner


def test_collect_writes_badge_file_per_package_with_window_in_filename(tmp_path: Path) -> None:
    config = _make_config(
        tmp_path,
        [
            PackageConfig(name="mcp-clipboard", window_days=30),
            PackageConfig(name="yt-dont-recommend", window_days=7),
        ],
    )
    runner = _fake_runner_for({"mcp-clipboard": 142, "yt-dont-recommend": 8})

    collect(config, runner=runner)

    clipboard_badge = config.service.output_dir / "mcp-clipboard" / "downloads-30d-non-ci.json"
    yt_badge = config.service.output_dir / "yt-dont-recommend" / "downloads-7d-non-ci.json"
    assert clipboard_badge.exists()
    assert yt_badge.exists()

    clipboard_payload = json.loads(clipboard_badge.read_text())
    assert clipboard_payload == {
        "schemaVersion": 1,
        "label": "downloads (30d, non-CI)",
        "message": "142",
        "color": "blue",
    }

    yt_payload = json.loads(yt_badge.read_text())
    assert yt_payload["message"] == "8"
    assert yt_payload["label"] == "downloads (7d, non-CI)"
    # Counts below the low-count threshold render grey to signal the data
    # point is small, not zero; falls out of the badge module's existing rule.
    assert yt_payload["color"] == "lightgrey"


def test_collect_writes_health_file_with_per_package_counts_and_timestamps(tmp_path: Path) -> None:
    config = _make_config(tmp_path, [PackageConfig(name="mcp-clipboard", window_days=30)])
    runner = _fake_runner_for({"mcp-clipboard": 142})

    fixed_start = datetime(2026, 4, 24, 21, 30, 0, tzinfo=UTC)
    fixed_end = datetime(2026, 4, 24, 21, 30, 2, tzinfo=UTC)
    times = iter([fixed_start, fixed_end])

    collect(config, runner=runner, clock=lambda: next(times))

    health_path = config.service.output_dir / "_health.json"
    assert health_path.exists()

    health = json.loads(health_path.read_text())
    assert health["started"] == fixed_start.isoformat()
    assert health["finished"] == fixed_end.isoformat()
    assert health["packages"] == {"mcp-clipboard": {"count": 142, "window_days": 30}}


def test_collect_continues_past_single_package_failure(tmp_path: Path) -> None:
    config = _make_config(
        tmp_path,
        [
            PackageConfig(name="broken-pkg", window_days=30),
            PackageConfig(name="good-pkg", window_days=30),
        ],
    )

    def partly_failing_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        ci_idx = argv.index("ci")
        pkg = argv[ci_idx - 1]
        if pkg == "broken-pkg":
            return subprocess.CompletedProcess(argv, 2, stdout="", stderr="boom")
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps({"rows": [{"ci": "False", "download_count": 99}], "query": {}}),
            stderr="",
        )

    result = collect(config, runner=partly_failing_runner)

    good_badge = config.service.output_dir / "good-pkg" / "downloads-30d-non-ci.json"
    broken_badge = config.service.output_dir / "broken-pkg" / "downloads-30d-non-ci.json"
    assert good_badge.exists()
    # Broken package should not have a badge file written — a stale badge
    # would be worse than a missing one, and the staleness mechanism on the
    # health file is what operators watch.
    assert not broken_badge.exists()

    assert len(result.failures) == 1
    assert result.failures[0].package == "broken-pkg"
    assert "boom" in (result.failures[0].error or "")

    # Health file records both outcomes.
    health = json.loads((config.service.output_dir / "_health.json").read_text())
    assert "error" in health["packages"]["broken-pkg"]
    assert health["packages"]["good-pkg"]["count"] == 99


def test_collect_result_reports_no_failures_on_full_success(tmp_path: Path) -> None:
    config = _make_config(tmp_path, [PackageConfig(name="mcp-clipboard", window_days=30)])
    runner = _fake_runner_for({"mcp-clipboard": 142})

    result = collect(config, runner=runner)

    assert result.failures == ()
    assert len(result.outcomes) == 1
    assert result.outcomes[0].package == "mcp-clipboard"
    assert result.outcomes[0].count == 142
