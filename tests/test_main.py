from datetime import UTC, datetime
from pathlib import Path

import pytest

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
