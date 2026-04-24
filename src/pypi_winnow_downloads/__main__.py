from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from .collector import CollectorResult, collect
from .config import ConfigError, load_config


def main(
    argv: Sequence[str] | None = None,
    *,
    collector_fn: Callable[..., CollectorResult] = collect,
) -> None:
    parser = argparse.ArgumentParser(
        prog="winnow-collect",
        description="Query BigQuery via pypinfo and emit shields.io endpoint JSON per package.",
    )
    parser.add_argument("--config", required=True, type=Path, help="Path to the YAML config file.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable DEBUG-level logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = load_config(args.config)
    except FileNotFoundError:
        sys.exit(f"winnow-collect: config file not found: {args.config}")
    except (ConfigError, OSError) as e:
        sys.exit(f"winnow-collect: config error: {e}")

    result = collector_fn(config)

    if result.failures:
        names = ", ".join(f.package for f in result.failures)
        sys.exit(f"winnow-collect: {len(result.failures)} package(s) failed: {names}")


if __name__ == "__main__":
    main()
