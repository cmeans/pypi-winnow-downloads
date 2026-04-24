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


def _require(raw: dict[str, Any], key: str) -> Any:
    if key not in raw:
        raise ConfigError(f"missing required section '{key}'")
    return raw[key]


def load_config(path: Path) -> Config:
    with open(path) as f:
        raw = yaml.safe_load(f)

    service_raw = _require(raw, "service")
    packages_raw = _require(raw, "packages")

    service = ServiceConfig(
        output_dir=Path(service_raw["output_dir"]),
        credential_file=Path(service_raw["credential_file"]),
        stale_threshold_days=int(service_raw["stale_threshold_days"]),
    )

    packages = tuple(
        PackageConfig(name=p["name"], window_days=int(p["window_days"])) for p in packages_raw
    )

    return Config(service=service, packages=packages)
