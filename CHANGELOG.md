# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial project scaffold: `pyproject.toml` (hatchling build, Python 3.11+,
  PyYAML runtime dep, pytest/ruff dev extras, Apache 2.0 license), `.gitignore`,
  `README.md` with a scope-describing summary, Keep-a-Changelog-format
  `CHANGELOG.md`, `CLAUDE.md` documenting the handoff workflow for future
  Claude Code sessions.
- `pypi_winnow_downloads.config` module — YAML config loader that parses a
  minimal schema into a frozen `Config(service=ServiceConfig, packages=tuple[PackageConfig, ...])`
  dataclass hierarchy, with a typed `ConfigError` raised on missing or
  malformed fields (dotted-path messages like `service.output_dir`,
  `packages[0].name`).
- `pypi_winnow_downloads.badge` module —
  `format_count(n)` renders download counts with `k`/`M` suffixes (trims
  trailing `.0`, rolls 999_999 up to `1M` on the rounding boundary,
  rejects negative inputs),
  `build_payload(count=, label=)` returns a shields.io endpoint-JSON dict
  (color `blue` / `lightgrey` based on the count-10 threshold),
  `write_badge(path=, payload=)` does atomic `.tmp` + `os.replace` writes
  with parent-dir auto-creation.
- Stub `pypi_winnow_downloads.__main__` so the `winnow-collect` console
  script installs and exits cleanly instead of raising `ModuleNotFoundError`
  before the real CLI lands.
- CI workflow (ruff, mypy, pytest × Python 3.11/3.12/3.13, codecov upload).
- PR-label automation workflows (pr-labels, pr-labels-ci, qa-gate) ported
  from mcp-clipboard; QA-state-machine labels installed on the repo.
- Publish workflows for PyPI (on `v*` tag) and TestPyPI (on `test-v*` tag)
  using OIDC trusted publishing.
- `mypy` + `types-PyYAML` in the `dev` optional dependencies so CI's
  typecheck job resolves.
- README badge row including a self-hosted "non-CI downloads" badge
  (dogfood — goes live once M3 deploys the service).
- `pypi_winnow_downloads.collector` module — shells out to `pypinfo` via
  `subprocess.run` with an injectable runner for testability. `run_pypinfo`
  invokes `pypinfo --json --days <N> --all -a <creds> <pkg> ci`, parses the
  JSON `rows`, and sums `download_count` across rows where `ci != "True"`.
  `collect(config)` iterates the configured packages, writes one shields.io
  endpoint JSON per package at
  `<output_dir>/<package>/downloads-<window>d-non-ci.json`, and writes a
  `_health.json` record at the output-dir root with `started` / `finished`
  timestamps plus per-package counts or errors. Single-package failures do
  not stop the run — they surface in the health file and in the returned
  `CollectorResult.failures` tuple.
- Real `winnow-collect` CLI in `pypi_winnow_downloads.__main__`: argparse
  entry point accepting `--config <path>` and `--verbose/-v`, loading the
  YAML config, invoking `collector.collect()`, and exiting non-zero with a
  package-name list if any package failed.
- `pypinfo>=20.0.0` added as a runtime dependency.
- `config.example.yaml` at the repo root — a minimal working config with
  placeholder paths, the three initial target packages
  (`mcp-clipboard`, `mcp-synology`, `yt-dont-recommend`), and commented
  explanations of each field.
- `uv.lock` committed at the repo root for reproducible deploys (per
  `decision:pypi-winnow-downloads:uv-lock`). The lockfile is not packaged
  into the wheel — PyPI consumers still resolve freshly against
  `pyproject.toml`.

### Fixed

- `run_pypinfo` no longer passes `-a/--auth` on `argv`. pypinfo 23.0.0
  short-circuits at `cli.py:130-133` when `--auth` is present — it sets the
  credential location and returns without running the query, regardless of
  the positional `<project> <fields>` arguments. The collector now passes
  the credential path via the `GOOGLE_APPLICATION_CREDENTIALS` env var,
  which pypinfo's `core.py` reads on the no-flag path. Tests gain a
  real-`subprocess.run` integration test (using a fake `pypinfo` shim on
  PATH) so the same class of bug recurs.
- `collect()` now wraps both `run_pypinfo` and `badge.write_badge` in the
  per-package try block. An IOError during the badge write (read-only
  output dir, disk full, perms) becomes a recorded outcome rather than
  propagating out of `collect()` and skipping the `_health.json` write.
- `_default_runner` runs `subprocess.run` with `timeout=180` (1.5× pypinfo's
  own 120s query timeout). On `subprocess.TimeoutExpired`, `run_pypinfo`
  raises `CollectorError` with the elapsed timeout, so a hung child cannot
  block the systemd timer's next firing.
- Non-dict rows in pypinfo's JSON output now raise `CollectorError`
  instead of being silently skipped. Silent skipping would mask upstream
  schema breaks; loud failure surfaces them at the collector boundary.

[Unreleased]: https://github.com/cmeans/pypi-winnow-downloads/compare/v0.0.0...HEAD
