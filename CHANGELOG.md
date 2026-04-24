# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial project scaffold (pyproject.toml, README, CHANGELOG, LICENSE).
- CI workflow (ruff, mypy, pytest × Python 3.11/3.12/3.13, codecov).
- PR-label automation workflows (pr-labels, pr-labels-ci, qa-gate) ported
  from mcp-clipboard; QA-state-machine labels installed on the repo.
- Publish workflows for PyPI (on `v*` tag) and TestPyPI (on `test-v*` tag)
  using OIDC trusted publishing.
- README badge row including a self-hosted "non-CI downloads" badge
  (dogfood — goes live once M3 deploys the service).

[Unreleased]: https://github.com/cmeans/pypi-winnow-downloads/compare/v0.0.0...HEAD
