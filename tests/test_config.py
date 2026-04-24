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


def test_load_config_raises_configerror_on_empty_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("")

    with pytest.raises(ConfigError, match="empty"):
        load_config(config_path)


def test_load_config_raises_configerror_on_top_level_non_mapping(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("just a string\n")

    with pytest.raises(ConfigError, match="top-level"):
        load_config(config_path)


def test_load_config_raises_configerror_on_missing_inner_service_field(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "service:\n"
        "  credential_file: /tmp/gcp.json\n"
        "  stale_threshold_days: 3\n"
        "packages:\n"
        "  - name: mcp-clipboard\n"
        "    window_days: 30\n"
    )

    with pytest.raises(ConfigError, match=r"service\.output_dir"):
        load_config(config_path)


def test_load_config_raises_configerror_on_non_int_stale_threshold(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "service:\n"
        "  output_dir: /tmp/out\n"
        "  credential_file: /tmp/gcp.json\n"
        "  stale_threshold_days: three\n"
        "packages:\n"
        "  - name: mcp-clipboard\n"
        "    window_days: 30\n"
    )

    with pytest.raises(ConfigError, match=r"service\.stale_threshold_days"):
        load_config(config_path)


def test_load_config_raises_configerror_on_packages_null_body(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "service:\n"
        "  output_dir: /tmp/out\n"
        "  credential_file: /tmp/gcp.json\n"
        "  stale_threshold_days: 3\n"
        "packages:\n"
    )

    with pytest.raises(ConfigError, match="packages"):
        load_config(config_path)


def test_load_config_raises_configerror_on_missing_inner_package_field(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "service:\n"
        "  output_dir: /tmp/out\n"
        "  credential_file: /tmp/gcp.json\n"
        "  stale_threshold_days: 3\n"
        "packages:\n"
        "  - window_days: 30\n"
    )

    with pytest.raises(ConfigError, match=r"packages\[0\]\.name"):
        load_config(config_path)


def test_load_config_accepts_empty_packages_list(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "service:\n"
        "  output_dir: /tmp/out\n"
        "  credential_file: /tmp/gcp.json\n"
        "  stale_threshold_days: 3\n"
        "packages: []\n"
    )

    config = load_config(config_path)

    assert config.packages == ()
