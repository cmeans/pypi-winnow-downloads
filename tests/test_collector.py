import json
import os
import subprocess
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pypi_winnow_downloads.collector import CollectorError, collect, run_pypinfo
from pypi_winnow_downloads.config import Config, PackageConfig, ServiceConfig


def _ok_result(argv: list[str], stdout: str = '{"rows": []}') -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")


# --- run_pypinfo argv + env contract ---


def test_run_pypinfo_invokes_pypinfo_with_expected_argv(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
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
    assert "mypkg" in argv
    # Pivot field comes after the package per pypinfo's positional convention.
    assert argv.index("mypkg") < argv.index("ci")
    # `-a` must NOT be in argv. With `-a` present, pypinfo short-circuits at
    # cli.py:130-133: it sets the credential location and returns without
    # running the query, regardless of positional args. The credential must
    # be passed via the GOOGLE_APPLICATION_CREDENTIALS env var instead.
    assert "-a" not in argv
    assert "--auth" not in argv


def test_run_pypinfo_passes_credential_via_env_var(tmp_path: Path) -> None:
    captured_envs: list[dict[str, str]] = []

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        captured_envs.append(env)
        return _ok_result(argv)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)

    assert len(captured_envs) == 1
    env = captured_envs[0]
    # pypinfo (core.py:56) reads GOOGLE_APPLICATION_CREDENTIALS from the
    # environment when -a is not on argv.
    assert env["GOOGLE_APPLICATION_CREDENTIALS"] == str(creds)
    # Parent env should still be inherited (PATH must reach the child so
    # the pypinfo binary itself is resolvable).
    assert "PATH" in env


def test_run_pypinfo_real_subprocess_passes_env_to_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Integration test: exercises the real subprocess.run path through
    _default_runner. Catches the class of bug found in PR #5 round 1, where
    every test injected a fake runner and the real subprocess invocation
    was never validated.

    Approach: drop a fake `pypinfo` shim on PATH that records what env var
    + argv it received and emits a known JSON. Verify the collector's real
    subprocess pipe carried our credential env through.
    """
    obs_file = tmp_path / "observed.txt"
    fake = tmp_path / "pypinfo"
    fake.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import json, os, sys
            with open({str(obs_file)!r}, "w") as f:
                f.write(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "<MISSING>"))
                f.write("\\n")
                f.write(",".join(sys.argv[1:]))
            print(json.dumps({{"rows": [{{"ci": "False", "download_count": 11}}], "query": {{}}}}))
            """
        )
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    count = run_pypinfo("realpkg", 30, credential_file=creds)

    assert count == 11, "default runner did not actually execute the subprocess"
    observed_env, observed_argv = obs_file.read_text().splitlines()
    assert observed_env == str(creds), "GOOGLE_APPLICATION_CREDENTIALS did not reach child"
    argv_parts = observed_argv.split(",")
    assert "-a" not in argv_parts and "--auth" not in argv_parts, (
        "auth flag leaked into argv — pypinfo would short-circuit"
    )
    assert "realpkg" in argv_parts
    assert "ci" in argv_parts


def test_run_pypinfo_sums_non_ci_rows_and_excludes_ci_true(tmp_path: Path) -> None:
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

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout=stdout)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    count = run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)

    assert count == 95


def test_run_pypinfo_returns_zero_when_rows_empty(tmp_path: Path) -> None:
    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout='{"rows": [], "query": {}}')

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    count = run_pypinfo("newpkg", 30, credential_file=creds, runner=fake_runner)

    assert count == 0


def test_run_pypinfo_raises_on_nonzero_exit(tmp_path: Path) -> None:
    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="auth failed")

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="auth failed"):
        run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)


def test_run_pypinfo_raises_on_malformed_json(tmp_path: Path) -> None:
    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout="not json at all")

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="malformed JSON"):
        run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)


def test_run_pypinfo_raises_when_rows_key_missing(tmp_path: Path) -> None:
    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout='{"query": {}}')

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="rows"):
        run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)


def test_run_pypinfo_raises_on_non_dict_row(tmp_path: Path) -> None:
    # Silently skipping non-dict rows masks upstream pypinfo schema changes.
    # Fail loudly so a future format break is caught at the collector boundary
    # rather than producing wrong (but plausible) counts.
    stdout = json.dumps(
        {"rows": [{"ci": "False", "download_count": 7}, "unexpected-string-row"], "query": {}}
    )

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout=stdout)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="unexpected"):
        run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)


def test_run_pypinfo_raises_on_subprocess_timeout(tmp_path: Path) -> None:
    def slow_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=list(argv), timeout=180)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="timed out"):
        run_pypinfo("mypkg", 30, credential_file=creds, runner=slow_runner)


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
    def runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
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
    assert yt_payload["color"] == "lightgrey"


def test_collect_writes_health_file_with_per_package_counts_and_timestamps(
    tmp_path: Path,
) -> None:
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

    def partly_failing_runner(
        argv: list[str], env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
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
    assert not broken_badge.exists()

    assert len(result.failures) == 1
    assert result.failures[0].package == "broken-pkg"
    assert "boom" in (result.failures[0].error or "")

    health = json.loads((config.service.output_dir / "_health.json").read_text())
    assert "error" in health["packages"]["broken-pkg"]
    assert health["packages"]["good-pkg"]["count"] == 99


def test_collect_records_badge_write_failure_and_still_writes_health(tmp_path: Path) -> None:
    """If an IOError fires during badge.write_badge — read-only output dir,
    disk full, perms — that failure must surface as a recorded outcome and
    must not prevent _health.json from being written. The health file is
    the operational diagnostic; losing it on the failure path defeats its
    purpose.
    """
    output_dir = tmp_path / "ro_output"
    output_dir.mkdir()
    # Pre-create the package subdir as a read-only file so the badge write
    # fails when the collector tries to mkdir its parent. The health file
    # itself writes at output_dir root, which remains writable.
    blocker = output_dir / "mcp-clipboard"
    blocker.write_text("not a directory")  # collision: mkdir(parents=True) hits a file

    config = Config(
        service=ServiceConfig(
            output_dir=output_dir,
            credential_file=tmp_path / "creds.json",
            stale_threshold_days=3,
        ),
        packages=(PackageConfig(name="mcp-clipboard", window_days=30),),
    )
    runner = _fake_runner_for({"mcp-clipboard": 99})

    result = collect(config, runner=runner)

    assert len(result.failures) == 1
    assert result.failures[0].package == "mcp-clipboard"
    assert result.failures[0].error is not None

    # Health file must still write — operators rely on it for the failure
    # signal at the operational layer.
    health_path = output_dir / "_health.json"
    assert health_path.exists()
    health = json.loads(health_path.read_text())
    assert "error" in health["packages"]["mcp-clipboard"]


def test_collect_result_reports_no_failures_on_full_success(tmp_path: Path) -> None:
    config = _make_config(tmp_path, [PackageConfig(name="mcp-clipboard", window_days=30)])
    runner = _fake_runner_for({"mcp-clipboard": 142})

    result = collect(config, runner=runner)

    assert result.failures == ()
    assert len(result.outcomes) == 1
    assert result.outcomes[0].package == "mcp-clipboard"
    assert result.outcomes[0].count == 142
