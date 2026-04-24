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

[Unreleased]: https://github.com/cmeans/pypi-winnow-downloads/compare/v0.0.0...HEAD
