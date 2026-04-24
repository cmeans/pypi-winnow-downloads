# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised when a config file is malformed or missing required fields."""


@dataclass(frozen=True)
class PackageConfig:
    name: str
    window_days: int


@dataclass(frozen=True)
class ServiceConfig:
    output_dir: Path
    credential_file: Path
    stale_threshold_days: int


@dataclass(frozen=True)
class Config:
    service: ServiceConfig
    packages: tuple[PackageConfig, ...]


def _require_section(raw: Any, name: str) -> Any:
    if not isinstance(raw, dict) or name not in raw:
        raise ConfigError(f"missing required section '{name}'")
    return raw[name]


def _require_field(mapping: Any, parent_path: str, field: str) -> Any:
    dotted = f"{parent_path}.{field}"
    if not isinstance(mapping, dict):
        raise ConfigError(f"'{parent_path}' must be a mapping, got {type(mapping).__name__}")
    if field not in mapping:
        raise ConfigError(f"missing required field '{dotted}'")
    return mapping[field]


def _to_int(value: Any, dotted_path: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        raise ConfigError(f"{dotted_path} must be an integer, got {value!r}") from e


def load_config(path: Path) -> Config:
    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise ConfigError("config file is empty")
    if not isinstance(raw, dict):
        raise ConfigError(f"top-level must be a mapping, got {type(raw).__name__}")

    service_raw = _require_section(raw, "service")
    packages_raw = _require_section(raw, "packages")

    service = ServiceConfig(
        output_dir=Path(_require_field(service_raw, "service", "output_dir")),
        credential_file=Path(_require_field(service_raw, "service", "credential_file")),
        stale_threshold_days=_to_int(
            _require_field(service_raw, "service", "stale_threshold_days"),
            "service.stale_threshold_days",
        ),
    )

    if packages_raw is None:
        raise ConfigError("'packages' must be a list, got null")
    if not isinstance(packages_raw, list):
        raise ConfigError(f"'packages' must be a list, got {type(packages_raw).__name__}")

    packages = tuple(
        PackageConfig(
            name=_require_field(p, f"packages[{i}]", "name"),
            window_days=_to_int(
                _require_field(p, f"packages[{i}]", "window_days"),
                f"packages[{i}].window_days",
            ),
        )
        for i, p in enumerate(packages_raw)
    )

    return Config(service=service, packages=packages)
