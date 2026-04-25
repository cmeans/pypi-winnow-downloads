import json
import subprocess
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pypi_winnow_downloads import collector as collector_module
from pypi_winnow_downloads.collector import (
    CollectorError,
    _resolve_pypinfo_path,
    collect,
    run_pypinfo_batch,
)
from pypi_winnow_downloads.config import Config, PackageConfig, ServiceConfig


def _ok_result(argv: list[str], stdout: str = '{"rows": []}') -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")


# --- _resolve_pypinfo_path ----------------------------------------------


def test_resolve_pypinfo_path_neighbors_sys_executable() -> None:
    """Resolver returns the pypinfo console script in the same directory
    as the running Python interpreter — the layout pip + uv +
    setuptools-based installers all produce when pypi-winnow-downloads
    pulls in pypinfo as a runtime dep.
    """
    resolved = Path(_resolve_pypinfo_path())
    assert resolved.is_absolute()
    assert resolved.parent == Path(sys.executable).parent
    assert resolved.name in ("pypinfo", "pypinfo.exe")


# --- run_pypinfo_batch argv + env contract ------------------------------


def test_run_pypinfo_batch_uses_where_in_clause_for_all_packages(tmp_path: Path) -> None:
    """One pypinfo invocation scans BigQuery for every package via a
    `WHERE file.project IN (...)` clause. This is the cost-per-N-packages
    invariant — without it the collector's BigQuery scan would scale
    linearly with the package count and quickly leave the 1 TB/month
    free tier.
    """
    captured: list[list[str]] = []

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        captured.append(list(argv))
        return _ok_result(argv)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    run_pypinfo_batch(
        ["mcp-clipboard", "mcp-synology", "yt-dont-recommend"],
        30,
        credential_file=creds,
        runner=fake_runner,
    )

    assert len(captured) == 1, "batch must produce exactly one runner invocation"
    argv = captured[0]
    # argv[0] is the resolver's absolute path, basename pypinfo.
    assert Path(argv[0]).is_absolute()
    assert Path(argv[0]).name in ("pypinfo", "pypinfo.exe")
    assert "--json" in argv
    assert argv[argv.index("--days") + 1] == "30"
    assert "--all" in argv
    # --where contains every requested package wrapped in double quotes
    # and joined by ", ", and uses file.project IN (...) syntax.
    where_value = argv[argv.index("--where") + 1]
    assert where_value.startswith("file.project IN (")
    assert '"mcp-clipboard"' in where_value
    assert '"mcp-synology"' in where_value
    assert '"yt-dont-recommend"' in where_value
    # Pivot order after the package positional placeholder.
    assert argv.index("project") < argv.index("ci") < argv.index("installer")
    # `-a/--auth` MUST NOT be in argv (would short-circuit pypinfo).
    assert "-a" not in argv
    assert "--auth" not in argv


def test_run_pypinfo_batch_passes_credential_via_env_var(tmp_path: Path) -> None:
    captured_envs: list[dict[str, str]] = []

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        captured_envs.append(env)
        return _ok_result(argv)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    run_pypinfo_batch(["pkg-a"], 30, credential_file=creds, runner=fake_runner)

    assert len(captured_envs) == 1
    env = captured_envs[0]
    assert env["GOOGLE_APPLICATION_CREDENTIALS"] == str(creds)
    assert "PATH" in env


def test_run_pypinfo_batch_real_subprocess_passes_env_to_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Integration test: exercises the real `subprocess.run` path through
    `_default_runner`. The `_resolve_pypinfo_path` helper is monkeypatched
    to a tmp_path-resident fake binary; the collector invokes that fake
    via subprocess and the test asserts the credential env reached the
    child and `-a/--auth` did NOT leak into argv.
    """
    obs_file = tmp_path / "observed.txt"
    fake = tmp_path / "fake-pypinfo"
    fake.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import json, os, sys
            with open({str(obs_file)!r}, "w") as f:
                f.write(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "<MISSING>"))
                f.write("\\n")
                f.write(",".join(sys.argv[1:]))
            row = {{
                "project": "realpkg",
                "ci": "False",
                "download_count": 11,
                "installer_name": "pip",
            }}
            print(json.dumps({{"rows": [row], "query": {{}}}}))
            """
        )
    )
    fake.chmod(0o755)
    monkeypatch.setattr(collector_module, "_resolve_pypinfo_path", lambda: str(fake))

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    counts = run_pypinfo_batch(["realpkg"], 30, credential_file=creds)

    assert counts == {"realpkg": 11}
    observed_env, observed_argv = obs_file.read_text().splitlines()
    assert observed_env == str(creds)
    argv_parts = observed_argv.split(",")
    assert "-a" not in argv_parts and "--auth" not in argv_parts
    assert "--where" in argv_parts
    assert "project" in argv_parts


def test_run_pypinfo_batch_isolates_state_so_env_var_wins_over_persisted_creds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pypinfo's `get_credentials()` reads a persisted credential path
    from `platformdirs.user_data_dir('pypinfo')/db.json` and returns it
    via `creds_file or os.environ.get(...)` — left-to-right `or` means
    a persisted path wins over GOOGLE_APPLICATION_CREDENTIALS. The
    collector overrides `XDG_DATA_HOME` per invocation so pypinfo's
    TinyDB query returns None and the env-var fallback applies.
    """
    polluted_xdg = tmp_path / "polluted-xdg"
    (polluted_xdg / "pypinfo").mkdir(parents=True)
    (polluted_xdg / "pypinfo" / "db.json").write_text(
        '{"credentials": {"1": {"path": "/wrong/path/from/persisted/db.json"}}}'
    )
    monkeypatch.setenv("XDG_DATA_HOME", str(polluted_xdg))

    obs_creds = tmp_path / "obs-creds.txt"
    fake = tmp_path / "fake-pypinfo"
    fake.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import json, os
            xdg = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
            db_path = os.path.join(xdg, "pypinfo", "db.json")
            persisted = None
            if os.path.exists(db_path):
                with open(db_path) as f:
                    data = json.load(f)
                for table in data.values():
                    for entry in table.values():
                        if isinstance(entry, dict) and "path" in entry:
                            persisted = entry["path"]
                            break
                    if persisted:
                        break
            creds = persisted or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            with open({str(obs_creds)!r}, "w") as f:
                f.write(creds or "<NONE>")
            row = {{"project": "pkg", "ci": "False", "download_count": 1, "installer_name": "pip"}}
            print(json.dumps({{"rows": [row], "query": {{}}}}))
            """
        )
    )
    fake.chmod(0o755)
    monkeypatch.setattr(collector_module, "_resolve_pypinfo_path", lambda: str(fake))

    expected_creds = tmp_path / "expected-creds.json"
    expected_creds.write_text("{}")

    counts = run_pypinfo_batch(["pkg"], 30, credential_file=expected_creds)

    assert counts == {"pkg": 1}
    assert obs_creds.read_text() == str(expected_creds), (
        "pypinfo's persisted db.json took priority over GOOGLE_APPLICATION_CREDENTIALS "
        "— XDG_DATA_HOME isolation in run_pypinfo_batch is missing or broken"
    )


# --- run_pypinfo_batch parsing -----------------------------------------


def test_run_pypinfo_batch_splits_counts_per_package(tmp_path: Path) -> None:
    """Multi-package response is split correctly: each row is summed
    into its own package's bucket based on `project`. CI rows are
    excluded; non-allowlisted installers are excluded.
    """
    stdout = json.dumps(
        {
            "rows": [
                {"project": "pkg-a", "ci": "False", "download_count": 50, "installer_name": "pip"},
                {"project": "pkg-a", "ci": "False", "download_count": 10, "installer_name": "uv"},
                {"project": "pkg-a", "ci": "True", "download_count": 9999, "installer_name": "pip"},
                {"project": "pkg-b", "ci": "False", "download_count": 7, "installer_name": "pip"},
                {
                    "project": "pkg-b",
                    "ci": "False",
                    "download_count": 600,
                    "installer_name": "bandersnatch",
                },
                {
                    "project": "pkg-c",
                    "ci": "False",
                    "download_count": 1,
                    "installer_name": "poetry",
                },
            ],
            "query": {},
        }
    )

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout=stdout)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    counts = run_pypinfo_batch(
        ["pkg-a", "pkg-b", "pkg-c"], 30, credential_file=creds, runner=fake_runner
    )

    assert counts == {
        "pkg-a": 60,  # 50 (pip) + 10 (uv); 9999 (CI) excluded
        "pkg-b": 7,  # 7 (pip); 600 (bandersnatch) excluded by allowlist
        "pkg-c": 1,  # 1 (poetry)
    }


def test_run_pypinfo_batch_includes_zero_count_packages(tmp_path: Path) -> None:
    """Packages with zero rows in the response still appear in the
    returned dict with count=0 — the caller relies on the dict to
    enumerate which packages were queried.
    """

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout='{"rows": [], "query": {}}')

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    counts = run_pypinfo_batch(["pkg-a", "pkg-b"], 30, credential_file=creds, runner=fake_runner)

    assert counts == {"pkg-a": 0, "pkg-b": 0}


def test_run_pypinfo_batch_returns_empty_for_empty_input(tmp_path: Path) -> None:
    """Calling the batch with no packages is a no-op (skips the
    subprocess) — defensive against config-loading edge cases."""
    invocations: list[None] = []

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        invocations.append(None)
        return _ok_result(argv)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    counts = run_pypinfo_batch([], 30, credential_file=creds, runner=fake_runner)

    assert counts == {}
    assert invocations == [], "no runner call expected for empty input"


def test_run_pypinfo_batch_raises_on_nonzero_exit(tmp_path: Path) -> None:
    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="auth failed")

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="auth failed"):
        run_pypinfo_batch(["pkg"], 30, credential_file=creds, runner=fake_runner)


def test_run_pypinfo_batch_raises_on_malformed_json(tmp_path: Path) -> None:
    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout="not json at all")

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="malformed JSON"):
        run_pypinfo_batch(["pkg"], 30, credential_file=creds, runner=fake_runner)


def test_run_pypinfo_batch_raises_when_rows_key_missing(tmp_path: Path) -> None:
    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout='{"query": {}}')

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="rows"):
        run_pypinfo_batch(["pkg"], 30, credential_file=creds, runner=fake_runner)


def test_run_pypinfo_batch_raises_on_non_dict_row(tmp_path: Path) -> None:
    stdout = json.dumps(
        {
            "rows": [
                {"project": "pkg", "ci": "False", "download_count": 7, "installer_name": "pip"},
                "unexpected-string-row",
            ],
            "query": {},
        }
    )

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout=stdout)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="unexpected"):
        run_pypinfo_batch(["pkg"], 30, credential_file=creds, runner=fake_runner)


def test_run_pypinfo_batch_raises_on_subprocess_timeout(tmp_path: Path) -> None:
    def slow_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=list(argv), timeout=180)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="timed out"):
        run_pypinfo_batch(["pkg"], 30, credential_file=creds, runner=slow_runner)


def test_run_pypinfo_batch_raises_on_missing_project_field(tmp_path: Path) -> None:
    """Without `project`, we can't split per-package. Schema break →
    fail loud instead of silent attribution to the wrong package."""
    stdout = json.dumps(
        {
            "rows": [{"ci": "False", "download_count": 7, "installer_name": "pip"}],
            "query": {},
        }
    )

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout=stdout)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="project"):
        run_pypinfo_batch(["pkg"], 30, credential_file=creds, runner=fake_runner)


def test_run_pypinfo_batch_raises_on_missing_installer_name_field(tmp_path: Path) -> None:
    stdout = json.dumps(
        {
            "rows": [{"project": "pkg", "ci": "False", "download_count": 50}],
            "query": {},
        }
    )

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout=stdout)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="installer_name"):
        run_pypinfo_batch(["pkg"], 30, credential_file=creds, runner=fake_runner)


def test_run_pypinfo_batch_raises_on_unrequested_package(tmp_path: Path) -> None:
    """If pypinfo returns a row for a package we didn't ask about,
    something has gone wrong with the WHERE clause or pypinfo. Better
    to fail loud than silently misattribute or undercount."""
    stdout = json.dumps(
        {
            "rows": [
                {
                    "project": "asked-pkg",
                    "ci": "False",
                    "download_count": 10,
                    "installer_name": "pip",
                },
                {
                    "project": "WRONG-pkg",
                    "ci": "False",
                    "download_count": 999,
                    "installer_name": "pip",
                },
            ],
            "query": {},
        }
    )

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout=stdout)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="WRONG-pkg"):
        run_pypinfo_batch(["asked-pkg"], 30, credential_file=creds, runner=fake_runner)


def test_run_pypinfo_batch_rejects_package_names_with_quote_characters(
    tmp_path: Path,
) -> None:
    """PyPI package names are PEP 508-restricted to [A-Za-z0-9._-]; a
    name with `"` or `\\` indicates either an invalid input source or
    deliberate injection attempt. Reject before SQL composition."""
    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    with pytest.raises(CollectorError, match="forbidden character"):
        run_pypinfo_batch(['ev"il'], 30, credential_file=creds, runner=lambda *_: _ok_result([]))


def test_run_pypinfo_batch_allowlist_is_case_sensitive(tmp_path: Path) -> None:
    stdout = json.dumps(
        {
            "rows": [
                {"project": "pkg", "ci": "False", "download_count": 100, "installer_name": "pip"},
                {"project": "pkg", "ci": "False", "download_count": 999, "installer_name": "Pip"},
                {"project": "pkg", "ci": "False", "download_count": 999, "installer_name": "PIP"},
            ],
            "query": {},
        }
    )

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout=stdout)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    counts = run_pypinfo_batch(["pkg"], 30, credential_file=creds, runner=fake_runner)

    assert counts == {"pkg": 100}


def test_run_pypinfo_batch_allowlist_covers_packaging_tool_family(tmp_path: Path) -> None:
    stdout = json.dumps(
        {
            "rows": [
                {"project": "pkg", "ci": "False", "download_count": 1, "installer_name": "pip"},
                {"project": "pkg", "ci": "False", "download_count": 2, "installer_name": "uv"},
                {"project": "pkg", "ci": "False", "download_count": 4, "installer_name": "poetry"},
                {"project": "pkg", "ci": "False", "download_count": 8, "installer_name": "pdm"},
                {"project": "pkg", "ci": "False", "download_count": 16, "installer_name": "pipenv"},
                {"project": "pkg", "ci": "False", "download_count": 32, "installer_name": "pipx"},
            ],
            "query": {},
        }
    )

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return _ok_result(argv, stdout=stdout)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    counts = run_pypinfo_batch(["pkg"], 30, credential_file=creds, runner=fake_runner)

    assert counts == {"pkg": 63}  # 1+2+4+8+16+32


# --- collect() orchestration -------------------------------------------


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
    """Return a runner that, given a batched argv with --where IN (...),
    emits one row per package with installer_name=pip and the
    pre-configured count."""

    def runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        where_value = argv[argv.index("--where") + 1]
        # Extract package names from the WHERE clause.
        pkgs_in_where = [p for p in counts_by_package if f'"{p}"' in where_value]
        rows = [
            {
                "project": p,
                "ci": "False",
                "download_count": counts_by_package[p],
                "installer_name": "pip",
            }
            for p in pkgs_in_where
        ]
        stdout = json.dumps({"rows": rows, "query": {}})
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
        "label": "pip*/uv/poetry/pdm (30d)",
        "message": "142",
        "color": "blue",
    }

    yt_payload = json.loads(yt_badge.read_text())
    assert yt_payload["message"] == "8"
    assert yt_payload["label"] == "pip*/uv/poetry/pdm (7d)"
    assert yt_payload["color"] == "lightgrey"


def test_collect_groups_packages_by_window_into_one_batch_per_window(
    tmp_path: Path,
) -> None:
    """Packages with the same window_days share a single pypinfo
    invocation; packages with different window_days each get their own
    batch. The cost-per-N invariant only applies within a window
    group — but in practice every package uses 30 days, so this is
    one query in the typical case.
    """
    config = _make_config(
        tmp_path,
        [
            PackageConfig(name="a", window_days=30),
            PackageConfig(name="b", window_days=30),
            PackageConfig(name="c", window_days=7),
        ],
    )

    runner_calls: list[tuple[list[str], int]] = []

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        days = int(argv[argv.index("--days") + 1])
        where = argv[argv.index("--where") + 1]
        runner_calls.append((argv, days))
        rows = [
            {"project": p, "ci": "False", "download_count": 1, "installer_name": "pip"}
            for p in ("a", "b", "c")
            if f'"{p}"' in where
        ]
        return _ok_result(argv, stdout=json.dumps({"rows": rows, "query": {}}))

    collect(config, runner=fake_runner)

    assert len(runner_calls) == 2, "expected one batch per distinct window_days"
    by_days = {days: argv for argv, days in runner_calls}
    assert set(by_days.keys()) == {30, 7}
    where_30 = by_days[30][by_days[30].index("--where") + 1]
    where_7 = by_days[7][by_days[7].index("--where") + 1]
    assert '"a"' in where_30 and '"b"' in where_30 and '"c"' not in where_30
    assert '"c"' in where_7 and '"a"' not in where_7 and '"b"' not in where_7


def test_collect_one_batch_for_all_packages_when_window_is_uniform(tmp_path: Path) -> None:
    """The common case: every configured package uses the same window
    (config.example.yaml has all three at 30 days). One pypinfo call,
    one BigQuery scan — the foundation of the cost story for hosting
    dozens of packages."""
    config = _make_config(
        tmp_path,
        [PackageConfig(name=f"pkg-{i}", window_days=30) for i in range(10)],
    )

    invocation_count = 0

    def counting_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        nonlocal invocation_count
        invocation_count += 1
        where = argv[argv.index("--where") + 1]
        rows = [
            {
                "project": f"pkg-{i}",
                "ci": "False",
                "download_count": i * 10,
                "installer_name": "pip",
            }
            for i in range(10)
            if f'"pkg-{i}"' in where
        ]
        return _ok_result(argv, stdout=json.dumps({"rows": rows, "query": {}}))

    collect(config, runner=counting_runner)

    assert invocation_count == 1, "10 packages with the same window must be one batch"


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


def test_collect_records_batch_failure_for_all_packages_in_window(tmp_path: Path) -> None:
    """When the BigQuery query fails, all packages in that window's
    batch are marked failed (we have no per-package counts). The other
    windows still run normally; _health.json still writes."""
    config = _make_config(
        tmp_path,
        [
            PackageConfig(name="failing-pkg-1", window_days=30),
            PackageConfig(name="failing-pkg-2", window_days=30),
            PackageConfig(name="ok-pkg", window_days=7),
        ],
    )

    def split_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        days = int(argv[argv.index("--days") + 1])
        if days == 30:
            return subprocess.CompletedProcess(argv, 2, stdout="", stderr="boom")
        # 7-day window succeeds.
        rows = [{"project": "ok-pkg", "ci": "False", "download_count": 99, "installer_name": "pip"}]
        return _ok_result(argv, stdout=json.dumps({"rows": rows, "query": {}}))

    result = collect(config, runner=split_runner)

    failures_by_pkg = {f.package for f in result.failures}
    assert failures_by_pkg == {"failing-pkg-1", "failing-pkg-2"}

    ok_pkg = next(o for o in result.outcomes if o.package == "ok-pkg")
    assert ok_pkg.count == 99
    assert (config.service.output_dir / "ok-pkg" / "downloads-7d-non-ci.json").exists()

    health = json.loads((config.service.output_dir / "_health.json").read_text())
    assert "error" in health["packages"]["failing-pkg-1"]
    assert "error" in health["packages"]["failing-pkg-2"]
    assert health["packages"]["ok-pkg"]["count"] == 99


def test_collect_records_badge_write_failure_and_still_writes_health(tmp_path: Path) -> None:
    """Per-package badge-write isolation. A read-only output subdir for
    one package marks that package as failed; the others get their
    badges; _health.json still writes."""
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    # Pre-create a file at the package subdir path so mkdir(parents=True)
    # for badge.write_badge fails for this package only.
    (output_dir / "broken-pkg").write_text("not a directory")

    config = Config(
        service=ServiceConfig(
            output_dir=output_dir,
            credential_file=tmp_path / "creds.json",
            stale_threshold_days=3,
        ),
        packages=(
            PackageConfig(name="broken-pkg", window_days=30),
            PackageConfig(name="ok-pkg", window_days=30),
        ),
    )
    runner = _fake_runner_for({"broken-pkg": 50, "ok-pkg": 99})

    result = collect(config, runner=runner)

    failures = {f.package for f in result.failures}
    assert failures == {"broken-pkg"}
    assert (output_dir / "ok-pkg" / "downloads-30d-non-ci.json").exists()

    health_path = output_dir / "_health.json"
    assert health_path.exists()
    health = json.loads(health_path.read_text())
    assert "error" in health["packages"]["broken-pkg"]
    assert health["packages"]["ok-pkg"]["count"] == 99


def test_collect_result_reports_no_failures_on_full_success(tmp_path: Path) -> None:
    config = _make_config(tmp_path, [PackageConfig(name="mcp-clipboard", window_days=30)])
    runner = _fake_runner_for({"mcp-clipboard": 142})

    result = collect(config, runner=runner)

    assert result.failures == ()
    assert len(result.outcomes) == 1
    assert result.outcomes[0].package == "mcp-clipboard"
    assert result.outcomes[0].count == 142
