# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import pytest

from pypi_winnow_downloads.config import ConfigError, load_config


def test_load_config_parses_minimal_valid_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "service:\n"
        "  output_dir: /var/lib/pypi-winnow-downloads/output\n"
        "  credential_file: /etc/pypi-winnow-downloads/gcp.json\n"
        "  stale_threshold_days: 3\n"
        "packages:\n"
        "  - name: mcp-clipboard\n"
        "    window_days: 30\n"
    )

    config = load_config(config_path)

    assert config.service.output_dir == Path("/var/lib/pypi-winnow-downloads/output")
    assert config.service.credential_file == Path("/etc/pypi-winnow-downloads/gcp.json")
    assert config.service.stale_threshold_days == 3
    assert len(config.packages) == 1
    assert config.packages[0].name == "mcp-clipboard"
    assert config.packages[0].window_days == 30


def test_load_config_parses_multiple_packages_with_differing_windows(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "service:\n"
        "  output_dir: /tmp/out\n"
        "  credential_file: /tmp/gcp.json\n"
        "  stale_threshold_days: 3\n"
        "packages:\n"
        "  - name: mcp-clipboard\n"
        "    window_days: 30\n"
        "  - name: mcp-synology\n"
        "    window_days: 30\n"
        "  - name: yt-dont-recommend\n"
        "    window_days: 7\n"
    )

    config = load_config(config_path)

    assert [p.name for p in config.packages] == [
        "mcp-clipboard",
        "mcp-synology",
        "yt-dont-recommend",
    ]
    assert [p.window_days for p in config.packages] == [30, 30, 7]


def test_load_config_raises_on_missing_service_section(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("packages:\n  - name: mcp-clipboard\n    window_days: 30\n")

    with pytest.raises(ConfigError, match="missing required section 'service'"):
        load_config(config_path)


def test_load_config_raises_on_missing_packages_section(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "service:\n"
        "  output_dir: /tmp/out\n"
        "  credential_file: /tmp/gcp.json\n"
        "  stale_threshold_days: 3\n"
    )

    with pytest.raises(ConfigError, match="missing required section 'packages'"):
        load_config(config_path)
