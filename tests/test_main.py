import runpy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pypi_winnow_downloads import collector as collector_module
from pypi_winnow_downloads.__main__ import main
from pypi_winnow_downloads.collector import CollectorResult, PackageOutcome


def _valid_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "service:\n"
        f"  output_dir: {tmp_path / 'out'}\n"
        f"  credential_file: {tmp_path / 'creds.json'}\n"
        "  stale_threshold_days: 3\n"
        "packages:\n"
        "  - name: mcp-clipboard\n"
        "    window_days: 30\n"
    )
    return cfg


def _empty_result() -> CollectorResult:
    now = datetime(2026, 4, 24, 21, 0, 0, tzinfo=UTC)
    return CollectorResult(started=now, finished=now, outcomes=())


def test_main_requires_config_flag() -> None:
    # argparse exits on missing required option; any SystemExit is acceptable
    # — we just want to confirm the CLI rejects the no-arg case rather than
    # silently doing nothing.
    with pytest.raises(SystemExit):
        main([])


def test_main_reports_missing_config_file(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.yaml"
    with pytest.raises(SystemExit, match="not found"):
        main([f"--config={missing}"])


def test_main_reports_config_parse_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("just a string, not a mapping")
    with pytest.raises(SystemExit, match="config error"):
        main([f"--config={bad}"])


def test_main_invokes_collector_with_loaded_config(tmp_path: Path) -> None:
    cfg = _valid_config(tmp_path)
    seen_configs = []

    def fake_collect(config):
        seen_configs.append(config)
        return _empty_result()

    main([f"--config={cfg}"], collector_fn=fake_collect)

    assert len(seen_configs) == 1
    assert [p.name for p in seen_configs[0].packages] == ["mcp-clipboard"]


def test_main_exits_zero_on_full_success(tmp_path: Path) -> None:
    cfg = _valid_config(tmp_path)

    # main returns None (no SystemExit) on full success.
    main([f"--config={cfg}"], collector_fn=lambda _cfg: _empty_result())


def test_main_exits_nonzero_when_any_package_fails(tmp_path: Path) -> None:
    cfg = _valid_config(tmp_path)

    def failing_collect(_cfg):
        now = datetime(2026, 4, 24, 21, 0, 0, tzinfo=UTC)
        return CollectorResult(
            started=now,
            finished=now,
            outcomes=(
                PackageOutcome(package="broken", window_days=30, count=None, error="boom"),
                PackageOutcome(package="good", window_days=30, count=42),
            ),
        )

    with pytest.raises(SystemExit, match="broken"):
        main([f"--config={cfg}"], collector_fn=failing_collect)


def test_main_exits_nonzero_when_health_file_write_fails(tmp_path: Path) -> None:
    """A health-write failure must produce a structured exit message via
    CollectorResult.health_write_error rather than letting an OSError escape
    through to a raw traceback. Bug class from issue #32.
    """
    cfg = _valid_config(tmp_path)

    def health_failed_collect(_cfg):
        now = datetime(2026, 4, 24, 21, 0, 0, tzinfo=UTC)
        return CollectorResult(
            started=now,
            finished=now,
            outcomes=(PackageOutcome(package="ok-pkg", window_days=30, count=99),),
            health_write_error="[Errno 28] No space left on device",
        )

    with pytest.raises(SystemExit, match=r"health file write failed.*No space left"):
        main([f"--config={cfg}"], collector_fn=health_failed_collect)


def test_main_combines_package_and_health_failure_messages(tmp_path: Path) -> None:
    """When both a per-package failure AND a health-write failure occur, the
    exit message reports both so the operator sees the full picture.
    """
    cfg = _valid_config(tmp_path)

    def both_failed_collect(_cfg):
        now = datetime(2026, 4, 24, 21, 0, 0, tzinfo=UTC)
        return CollectorResult(
            started=now,
            finished=now,
            outcomes=(
                PackageOutcome(package="broken-pkg", window_days=30, count=None, error="boom"),
            ),
            health_write_error="[Errno 13] Permission denied",
        )

    with pytest.raises(
        SystemExit, match=r"broken-pkg.*health file write failed.*Permission denied"
    ):
        main([f"--config={cfg}"], collector_fn=both_failed_collect)


def test_main_module_invokes_main_when_run_as_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`if __name__ == "__main__": main()` at __main__.py:52 fires when the
    package is invoked as `python -m pypi_winnow_downloads`. Use
    `runpy.run_module` with `run_name="__main__"` to exercise the same code
    path in-process so the line is observed by coverage.

    Stub `collector.collect` to a no-op CollectorResult so we don't shell out
    to pypinfo; main() will see no failures and return without SystemExit.
    """
    cfg = _valid_config(tmp_path)
    now = datetime(2026, 4, 24, 21, 0, 0, tzinfo=UTC)

    def stub_collect(_config: object) -> CollectorResult:
        return CollectorResult(started=now, finished=now, outcomes=())

    # __main__.py does `from .collector import collect`, which reads the
    # `collect` attribute on the collector module at import time. Patching
    # collector_module.collect BEFORE runpy.run_module ensures the freshly
    # executed __main__.py picks up the stub.
    monkeypatch.setattr(collector_module, "collect", stub_collect)
    monkeypatch.setattr("sys.argv", ["winnow-collect", "--config", str(cfg)])

    # run_name="__main__" makes the guard at line 52 evaluate True. With
    # zero failures returned by the stub, main() falls through cleanly
    # (no SystemExit).
    runpy.run_module("pypi_winnow_downloads", run_name="__main__")
