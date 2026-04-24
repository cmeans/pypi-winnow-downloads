import json
from pathlib import Path

from pypi_winnow_downloads.badge import build_payload, format_count, write_badge


def test_format_count_renders_small_numbers_as_literal() -> None:
    assert format_count(42) == "42"


def test_format_count_uses_k_suffix_for_thousands() -> None:
    assert format_count(12300) == "12.3k"


def test_format_count_trims_trailing_zero_in_k_suffix() -> None:
    assert format_count(1000) == "1k"
    assert format_count(12000) == "12k"


def test_format_count_uses_m_suffix_for_millions() -> None:
    assert format_count(1_500_000) == "1.5M"
    assert format_count(1_000_000) == "1M"


def test_build_payload_returns_shields_io_endpoint_structure() -> None:
    payload = build_payload(count=12300, label="non-CI downloads")

    assert payload == {
        "schemaVersion": 1,
        "label": "non-CI downloads",
        "message": "12.3k",
        "color": "blue",
    }


def test_build_payload_uses_lightgrey_for_low_counts() -> None:
    payload = build_payload(count=5, label="non-CI downloads")

    assert payload["color"] == "lightgrey"
    assert payload["message"] == "5"


def test_write_badge_writes_json_payload_to_path(tmp_path: Path) -> None:
    target = tmp_path / "badge.json"
    payload = {"schemaVersion": 1, "label": "x", "message": "42", "color": "blue"}

    write_badge(path=target, payload=payload)

    assert json.loads(target.read_text()) == payload


def test_write_badge_creates_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "mcp-clipboard" / "downloads-30d.json"
    payload = {"schemaVersion": 1, "label": "x", "message": "42", "color": "blue"}

    write_badge(path=target, payload=payload)

    assert target.exists()


def test_write_badge_leaves_no_temp_files_behind(tmp_path: Path) -> None:
    target = tmp_path / "badge.json"
    payload = {"schemaVersion": 1, "label": "x", "message": "42", "color": "blue"}

    write_badge(path=target, payload=payload)

    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == ["badge.json"]
