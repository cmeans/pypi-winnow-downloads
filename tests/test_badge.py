# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

import pytest

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


def test_format_count_rolls_over_from_k_to_m_on_rounding_boundary() -> None:
    # 999_999 rounds up to 1000.0k which should promote to "1M", not show as "1000.0k".
    assert format_count(999_999) == "1M"


def test_format_count_rounds_k_suffix_to_whole_without_trailing_zero() -> None:
    # 99_950 rounds to 100.0k — should render as "100k", not "100.0k".
    assert format_count(99_950) == "100k"


def test_format_count_rejects_negative_counts() -> None:
    # Download counts are non-negative by definition. A negative value is a
    # collector bug upstream; fail loudly rather than silently rendering "-5".
    with pytest.raises(ValueError, match="non-negative"):
        format_count(-5)


def test_format_count_renders_zero_as_literal() -> None:
    assert format_count(0) == "0"


def test_format_count_at_literal_boundary_ten() -> None:
    # 10 is the lightgrey/blue color threshold in build_payload; format itself
    # doesn't care about the threshold, but pinning the value avoids surprises.
    assert format_count(10) == "10"


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


def test_build_payload_at_lightgrey_boundary_is_blue() -> None:
    # count < 10 -> lightgrey, count == 10 -> blue. Pin the exact threshold
    # so off-by-one regressions surface immediately.
    payload = build_payload(count=10, label="non-CI downloads")
    assert payload["color"] == "blue"


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
