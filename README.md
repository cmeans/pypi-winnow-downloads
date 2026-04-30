# pypi-winnow-downloads

[![PyPI version](https://img.shields.io/pypi/v/pypi-winnow-downloads)](https://pypi.org/project/pypi-winnow-downloads/)
[![Python versions](https://img.shields.io/pypi/pyversions/pypi-winnow-downloads)](https://pypi.org/project/pypi-winnow-downloads/)
[![License](https://img.shields.io/pypi/l/pypi-winnow-downloads)](https://github.com/cmeans/pypi-winnow-downloads/blob/main/LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/cmeans/pypi-winnow-downloads/ci.yml?label=CI)](https://github.com/cmeans/pypi-winnow-downloads/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/cmeans/pypi-winnow-downloads/graph/badge.svg)](https://codecov.io/gh/cmeans/pypi-winnow-downloads)
[![pip*/uv/poetry/pdm downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Fdownloads-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)

Self-hosted PyPI download badge service that winnows CI traffic out of download
counts. Produces [shields.io](https://shields.io/badges/endpoint-badge)-compatible endpoint
badges filtered by BigQuery's `details.ci` flag *and* an interactive-installer
allowlist (`pip`, `uv`, `poetry`, `pdm`, `pipenv`, `pipx`) — more honest than
any existing alternative for small or young Python packages.

> **Eating our own dogfood** — the download-count badge in the row above and
> the breakdown below are produced by this project itself; the reference
> deployment at `pypi-badges.intfar.com` refreshes them daily via systemd timer.
> Both views track the same `pypi-winnow-downloads` package over a 30-day non-CI
> window.

**By installer** (30d, non-CI):

[![pip downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Finstaller-pip-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)
[![pipenv downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Finstaller-pipenv-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)
[![pipx downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Finstaller-pipx-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)
[![uv downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Finstaller-uv-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)
[![poetry downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Finstaller-poetry-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)
[![pdm downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Finstaller-pdm-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)

**By OS** (30d, non-CI):

[![linux downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Fos-linux-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)
[![macos downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Fos-macos-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)
[![windows downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Fos-windows-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)

## What these badges actually count

The hero badge — labelled `pip*/uv/poetry/pdm (Nd)` (N=30 in the reference
deployment, configurable per-package via `window_days`) — counts downloads that meet
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

**Per-installer breakdown.** Alongside the hero, the reference deployment also
produces one badge per installer in the allowlist (`pip`, `pipenv`, `pipx`,
`uv`, `poetry`, `pdm`) plus a `pip*` aggregate (`pip + pipenv + pipx`). Each
applies the same `details.ci != True` filter as the hero — so they answer
"non-CI downloads broken down by which packaging tool the user was running."
Useful for spotting installer-mix shifts (e.g., uv overtaking pip on a young
package). See [Use this service for your own package](#use-this-service-for-your-own-package)
below for the per-installer URL pattern.

**By OS breakdown.** Each per-OS badge applies the same `details.ci != True` filter as the hero — they answer "non-CI downloads on that OS." `Darwin` is pypinfo's emission for what users call macOS; the badge filename and label use `macos`. The per-OS sum can be less than the hero count: rows whose user-agent didn't expose a system_name (or exposed one outside Linux/Darwin/Windows) drop out of the per-OS aggregation but still count toward the hero — same pattern as the per-installer-sum ≤ hero gap.

## Install

```bash
uv tool install pypi-winnow-downloads
```

[`uv tool`](https://docs.astral.sh/uv/concepts/tools/) drops the
`winnow-collect` console-script onto your `PATH` in an isolated environment
without touching your system Python. If you don't have uv installed, plain pip
also works:

```bash
pip install pypi-winnow-downloads
```

The collector queries Google's public PyPI BigQuery dataset via
`pypinfo`, so before the first run you'll need a Google Cloud service
account JSON key. Pypinfo's
[installation guide](https://github.com/ofek/pypinfo#installation)
walks the full setup (create a GCP project, enable the BigQuery API,
generate the JSON key) and recommends the broad `BigQuery User` role;
the narrower pair `BigQuery Job User` + `BigQuery Data Viewer` also
works and is what `config.example.yaml` and the reference deploy
document. Then point `service.credential_file` in your config at the
resulting file.

Run with a YAML config — copy
[`config.example.yaml`](https://github.com/cmeans/pypi-winnow-downloads/blob/main/config.example.yaml)
and edit:

```bash
winnow-collect --config /path/to/config.yaml
```

To deploy as a daily systemd timer plus a Caddy HTTPS service serving the
output directory, see
[`deploy/README.md`](https://github.com/cmeans/pypi-winnow-downloads/blob/main/deploy/README.md).

## Use this service for your own package

The reference deployment at `pypi-badges.intfar.com` produces eight badge
JSON files per configured package per window, all under
`https://pypi-badges.intfar.com/<package>/`:

| File | Label | What it counts |
|---|---|---|
| `downloads-30d-non-ci.json` | `pip*/uv/poetry/pdm (30d)` | All six allowlisted installers summed (the v1 hero) |
| `installer-pip-30d-non-ci.json` | `pip (30d)` | `pip` only |
| `installer-pipenv-30d-non-ci.json` | `pipenv (30d)` | `pipenv` only |
| `installer-pipx-30d-non-ci.json` | `pipx (30d)` | `pipx` only |
| `installer-uv-30d-non-ci.json` | `uv (30d)` | `uv` only |
| `installer-poetry-30d-non-ci.json` | `poetry (30d)` | `poetry` only |
| `installer-pdm-30d-non-ci.json` | `pdm (30d)` | `pdm` only |
| `installer-pip-family-30d-non-ci.json` | `pip* (30d)` | `pip + pipenv + pipx` aggregate |
| `os-linux-30d-non-ci.json` | `linux (30d)` | Per-OS, Linux |
| `os-macos-30d-non-ci.json` | `macos (30d)` | Per-OS, macOS (Darwin) |
| `os-windows-30d-non-ci.json` | `windows (30d)` | Per-OS, Windows |

All files exclude CI traffic (BigQuery's `details.ci != True`). Each is a
[shields.io endpoint badge](https://shields.io/badges/endpoint-badge) JSON.

To embed any of these in your own README, wrap the file URL in shields.io's
`/endpoint?url=` form, URL-encoding the inner URL (`/` becomes `%2F`, `:`
becomes `%3A`):

```markdown
[![pip downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2F<your-package>%2Finstaller-pip-30d-non-ci.json)](https://pypi.org/project/<your-package>/)
```

Replace `<your-package>` with your PyPI package name. The same template
works for any of the eight files — substitute the filename. The window
length (`30d` in the examples) reflects the reference deployment's
`window_days: 30` setting; if you self-host, your own deployment's
`window_days` substitutes here.

To get your package added to the reference deployment's `config.yaml`,
[open an issue](https://github.com/cmeans/pypi-winnow-downloads/issues/new)
or run your own collector — see
[`deploy/README.md`](https://github.com/cmeans/pypi-winnow-downloads/blob/main/deploy/README.md).

## Status

Beta as of v0.2.0. Self-hosted reference deployment running at
`pypi-badges.intfar.com` since 2026-04-25, producing daily badges for
four target packages (the three seed packages in `config.example.yaml`
plus `pypi-winnow-downloads` itself for the dogfood badge). Test suite
holds 100% line coverage on `src/`. The v1 hero badge JSON shape and
filename are stable and won't change before 1.0; new badge files may
be added (the v2 installer-mix breakdown landed in v0.2.0 alongside
the unchanged hero). Expect occasional breaking changes elsewhere in
the 0.x series — the [`Changed`/`Removed` sections of CHANGELOG.md](https://github.com/cmeans/pypi-winnow-downloads/blob/main/CHANGELOG.md)
are where to look on each release.

## Acknowledgments

This project rests on three pieces of upstream work:

- [pypinfo](https://github.com/ofek/pypinfo) by Ofek Lev: the BigQuery
  query layer for the PyPI download dataset. `pypi-winnow-downloads` is
  essentially a filter and badge writer wrapped around pypinfo.
- [shields.io](https://shields.io/) renders the endpoint badges. The
  collector emits the JSON shape that shields.io's
  [endpoint badge](https://shields.io/badges/endpoint-badge) consumes,
  so badges inherit its caching, theming, and SVG rendering.
- The [`bigquery-public-data.pypi.file_downloads`](https://docs.pypi.org/api/bigquery/)
  dataset, hosted by Google as a public BigQuery dataset and populated
  by the PyPI Linehaul pipeline, is the underlying data source.
  Without it, no installer-level breakdown of PyPI downloads would be
  possible.

Designed and built collaboratively with
[Claude Code](https://claude.com/claude-code) (Anthropic) across
planning, implementation, review, and QA. Significant subsystems (the
pypinfo `XDG_DATA_HOME` isolation, the `sys.executable`-based pypinfo
resolver, the installer-allowlist filter, the deploy/ examples)
emerged through that planner / Dev / QA loop.

## License

Licensed under the
[Apache License, Version 2.0](https://github.com/cmeans/pypi-winnow-downloads/blob/main/LICENSE).

© 2026 Chris Means.
