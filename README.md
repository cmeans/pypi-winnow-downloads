# pypi-winnow-downloads

[![PyPI version](https://img.shields.io/pypi/v/pypi-winnow-downloads)](https://pypi.org/project/pypi-winnow-downloads/)
[![Python versions](https://img.shields.io/pypi/pyversions/pypi-winnow-downloads)](https://pypi.org/project/pypi-winnow-downloads/)
[![License](https://img.shields.io/pypi/l/pypi-winnow-downloads)](https://github.com/cmeans/pypi-winnow-downloads/blob/main/LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/cmeans/pypi-winnow-downloads/ci.yml?label=CI)](https://github.com/cmeans/pypi-winnow-downloads/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/cmeans/pypi-winnow-downloads/graph/badge.svg)](https://codecov.io/gh/cmeans/pypi-winnow-downloads)
[![non-CI downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Fdownloads-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)

Self-hosted PyPI download badge service that winnows CI traffic out of download
counts. Produces [shields.io](https://shields.io/endpoint)-compatible endpoint
badges filtered by BigQuery's `details.ci` field — more honest than any existing
alternative for small or young Python packages.

> The "non-CI downloads" badge above is served by this project itself —
> eating our own dogfood. The endpoint went live with milestone M3 deployment
> on 2026-04-24 and currently shows `0` until the first release lands on PyPI;
> after that the count climbs automatically.

## What the badge actually counts

The hero badge — labelled `pip*/uv/poetry/pdm (Nd)` — counts downloads that meet
**all** of these conditions over the configured rolling window:

- `details.ci != True` (BigQuery's CI-detection flag is not set)
- `details.installer.name` is one of the interactive Python packaging tools:
  `pip`, `uv`, `poetry`, `pdm`, `pipenv`, or `pipx` (the asterisk in `pip*`
  covers `pip` itself plus `pipenv` and `pipx`, which delegate to pip and
  inherit its installer telemetry pattern)

**Excluded** (the things that inflate other badges):

- Mirrors: `bandersnatch`, `Nexus`, `devpi`, `Artifactory`, `z3c.pypimirror`
- Browser fetches via the PyPI web UI (`installer_name == "Browser"`)
- Generic HTTP UAs used by scrapers and scanners (`requests`, `curl`, etc.)
- Unknown installer (`installer_name == "None"`) — uncategorised traffic that
  in practice is dominated by automated scanners

For context on how much these can dwarf real installs: at v1 deploy time, one
of the seed packages had 2,771 "non-CI" downloads in 30 days under a naïve
mirror-and-all-installers query, of which 1,325 (48%) was bandersnatch alone
and only 14 came from `pip + uv + poetry + pdm`. The honest signal is the 14.

The filter is **fail-closed**: a future pypinfo emitting a new mainstream
installer will be excluded until the allowlist in
`src/pypi_winnow_downloads/collector.py` is updated explicitly. That's a feature
for a project whose pitch is honesty.

Pre-alpha. Not yet usable.
