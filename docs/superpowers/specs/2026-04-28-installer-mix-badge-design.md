# Design — installer-mix badge (v2 candidate #1)

**Date:** 2026-04-28
**Status:** Approved by Chris (terminal sign-off, "B3 / C1 / Form A absolute counts" sequence; final approval after the README addendum was added).
**Target release:** v0.2.0 (minor bump — additive surface, but `run_pypinfo`'s return type changes from `int` to `dict[str, int]`).

## Background

The v1 hero badge (`pip*/uv/poetry/pdm (Nd)`) summed downloads from six interactive packaging tools — `pip`, `pipenv`, `pipx`, `uv`, `poetry`, `pdm` — into a single non-CI count per package per window. The data already resolved per-installer in BigQuery (`details.installer.name` is a primary pivot in the pypinfo query as of v0.1.0), but the collector threw the breakdown away after summing.

This spec covers the first v2 badge candidate from `project:pypi-winnow-downloads`'s "Future badge candidates" backlog: the **installer-mix** badge family. Goal: preserve the per-installer breakdown that's already in pypinfo's output and emit one badge JSON per installer (plus a `pip-family` aggregate), so package maintainers can show "here's what's actually installing my package."

## Scope

In scope:
- Per-installer count breakdown for each configured package, over the same window the v1 hero uses.
- Seven new badge JSON files per package per window (six individual installers + one `pip-family` aggregate).
- v1 hero file (`downloads-<N>d-non-ci.json`) preserved verbatim — additive change, no breaking surface.
- Health-file (`_health.json`) schema additively expanded to record the per-installer counts.
- README updated to dogfood all six individual installer counts and to document how third-party packages reference the service.

Out of scope (explicitly):
- Configurability per package of which files emit. Always emit all eight; maintainer's README picks which to display.
- "With-CI" variants. CI filter applied identically to v1.
- Per-installer brand colors. Same blue/lightgrey threshold as v1.
- Other v2 badge candidates (latest-version adoption, OS distribution, geography). Each gets its own spec.
- Changes to `mcp-clipboard` / `mcp-synology` / `yt-dont-recommend` READMEs. Those repos are out-of-cwd; this PR is `pypi-winnow-downloads` only.

## Decisions made during brainstorming

- **Form** (terminal sign-off, visual companion option A): four badges per package displayed in README — one per installer family. Maintainer concatenates them in a row.
- **Counts**: absolute integers (formatted via existing `badge.format_count()` — `1234` becomes `1.2k`). Not percentages.
- **Bucketing**: B3 — collector emits all six individual installers AND the pip-family aggregate. README owner picks which to show. The seventh aggregate is free since the collector already has the per-installer counts in memory.
- **CI filter**: C1 — non-CI only, mirrors v1 philosophy. CI breakdown deferred to a hypothetical v3 feature if anyone asks.
- **Configuration**: no new config fields. Always emit eight files (seven v2 + one v1 hero).
- **Color**: same threshold rule as v1 (`blue` if count ≥ 10 else `lightgrey`). No per-installer brand colors — they age oddly and add visual noise without adding signal.
- **Backwards compat**: v1 hero file kept side-by-side. Health-file `count` field at top level preserved verbatim; new `counts` map is additive.

## User-facing surface

Per package per configured window, the collector writes eight badge JSON files into `<output_dir>/<package>/`:

| Filename | Source | Label | Count |
|---|---|---|---|
| `downloads-<N>d-non-ci.json` | v1 (unchanged) | `pip*/uv/poetry/pdm (Nd)` | Sum across all six installers |
| `installer-pip-<N>d-non-ci.json` | v2 | `pip (Nd)` | `pip` only |
| `installer-pipenv-<N>d-non-ci.json` | v2 | `pipenv (Nd)` | `pipenv` only |
| `installer-pipx-<N>d-non-ci.json` | v2 | `pipx (Nd)` | `pipx` only |
| `installer-uv-<N>d-non-ci.json` | v2 | `uv (Nd)` | `uv` only |
| `installer-poetry-<N>d-non-ci.json` | v2 | `poetry (Nd)` | `poetry` only |
| `installer-pdm-<N>d-non-ci.json` | v2 | `pdm (Nd)` | `pdm` only |
| `installer-pip-family-<N>d-non-ci.json` | v2 | `pip* (Nd)` | `pip + pipenv + pipx` |

Each file is the standard shields.io endpoint JSON shape `{schemaVersion, label, message, color}`. The CI filter is applied identically to v1 — none of the v2 files include CI traffic.

## Data flow

`pypinfo --json --days <N> --all <pkg> ci installer` already returns rows with both `ci` and `installer_name` columns. The v1 collector iterates these rows, applies the allowlist filter (`installer_name in {pip, pipenv, pipx, uv, poetry, pdm}`) and the CI filter (`ci != "True"`), and sums the `download_count` values into a single `int`.

v2 changes the aggregation step:

1. `run_pypinfo` returns `dict[str, int]` mapping `installer_name → count`. Allowlist + CI filtering unchanged. Rows for installers outside the allowlist (mirrors, browsers, scrapers, unknown) still ignored. Rows where `ci == "True"` still ignored. An installer in the allowlist with no matching rows reports `0` (so the dict is always 6-keyed).
2. `collect()` per package:
   - Calls `run_pypinfo`, gets `per_installer: dict[str, int]`.
   - Computes `pip_family = per_installer["pip"] + per_installer["pipenv"] + per_installer["pipx"]`.
   - Computes `hero_total = sum(per_installer.values())` (unchanged from v1).
   - Writes eight badge files via the existing `badge.write_badge()`.
   - Records counts in the per-package health entry.

No new BigQuery query and no extra `pypinfo` invocation. The per-installer breakdown is already in the existing query's output; v2 stops throwing it away.

## Health file

Current `_health.json` per-package entry: `{count: int, error: str | null}`.

v2 expands additively:

```json
{
  "count": <hero_total>,
  "counts": {
    "pip": <int>,
    "pipenv": <int>,
    "pipx": <int>,
    "uv": <int>,
    "poetry": <int>,
    "pdm": <int>,
    "pip-family": <int>
  },
  "error": null
}
```

The top-level `count` field is preserved verbatim — anything reading `_health.json` today (including the live CT 112 deploy and any external monitoring) keeps working without modification. `counts` is purely additive.

## Configuration

No new fields in `Config` / `PackageConfig`. The collector always emits all eight files. Maintainer's README picks which to display via shields.io endpoint URLs.

This is a deliberate non-decision: configurability adds knobs without adding value at v2 scope, since file emission is essentially free (one extra `os.replace` per installer per package per run). If a future maintainer requests per-package opt-out, that's a small additive feature.

## README addendum (in scope for this PR)

Two prose changes in `README.md`:

1. **Dogfood badge row expanded.** Below the existing v1 hero badge, add six individual installer badges for `pypi-winnow-downloads` itself (one per installer in the allowlist). Pip-family aggregate is *not* shown in the dogfood row — readers see the granular breakdown to learn what's available; the aggregate is mentioned in the instructions section.

2. **New "Use this service for your own package" section** between `## Install` and `## Status`. Documents the URL pattern for shields.io endpoint badges:

   ```
   https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2F<package>%2F<filename>
   ```

   Lists copy-pasteable Markdown for each of the eight files (v1 hero + six individual + pip-family aggregate), with `<package>` parameterized. The section also documents the URL-encoding (the `%2F` literal is load-bearing — shields.io's endpoint argument must be URL-encoded, and the README's existing v1 hero badge already does this; new instructions match that convention).

## Implementation slice

`src/pypi_winnow_downloads/collector.py`:
- `run_pypinfo`: return type `int → dict[str, int]`. Allowlist filter unchanged (still `frozenset({"pip", "pipenv", "pipx", "uv", "poetry", "pdm"})`). Always returns a six-keyed dict — installers with no rows in the response get `0`.
- `_BADGE_FILENAME_TEMPLATE`: replaced/augmented to support per-installer filenames. Shape: `installer-<name>-<N>d-non-ci.json`.
- `collect()`: builds per-installer dict, computes `pip-family` and v1 hero aggregates, writes eight badge files. ~25 lines added, no architectural reshape — this stays a single straight-line function for now (refactor to a generator-list abstraction can come later if v2 grows another badge family).
- `CollectorResult`: no signature change. Per-package failure semantics unchanged — any `pypinfo` failure becomes a single per-package `CollectorError`, not fanned out per installer.
- `_write_health` / `_health.json` schema: additively expanded as documented above.

`src/pypi_winnow_downloads/badge.py`: no changes.

`src/pypi_winnow_downloads/__main__.py`: no changes.

`README.md`: two prose changes as documented above.

`CHANGELOG.md`: one `### Added` entry under `[Unreleased]` describing the new badge files, the README updates, the v0.2.0 minor bump rationale, and the v1 hero backwards-compat guarantee.

`pyproject.toml` + `uv.lock`: not bumped in this PR. Version bump happens at the v0.2.0 release PR.

## Tests

All existing 71 tests must continue to pass. New / changed coverage:

- `test_run_pypinfo_returns_per_installer_dict` (new, replaces existing int-returning assertion). Asserts the dict is six-keyed, that allowlisted installers with no rows get `0`, and that allowlist-excluded installers (mirrors, etc.) don't appear as keys.
- `test_collect_writes_eight_files_per_successful_package` (new). Asserts all eight expected filenames appear in the package output directory after a successful run.
- `test_pip_family_aggregate_equals_pip_plus_pipenv_plus_pipx` (new). Asserts the aggregate badge content equals the arithmetic sum.
- `test_v1_hero_count_unchanged_against_pre_v2_fixture` (new regression). Same pypinfo-row fixture, hero count must equal pre-v2 expectation. Locks the backwards-compat guarantee.
- `test_health_file_includes_per_installer_counts_map` (new). Asserts `_health.json` contains the new `counts` map with the expected seven keys (six installers + `pip-family`).
- `test_health_file_top_level_count_preserved` (new). Asserts top-level `count` field still equals the v1 hero total.
- Coverage gate (`fail_under = 100`) maintained.
- Existing tests that asserted `run_pypinfo` returned an `int` get updated to assert against the dict's `sum()`.

## PR shape

Single PR titled `feat(collector): add per-installer badge files` (or similar). One commit acceptable; multi-commit fine if it makes review easier (`feat(collector): emit per-installer counts` + `docs(readme): dogfood + endpoint instructions for v2 badges`). Squash-merge as usual.

CHANGELOG entry under `### Added`. v0.2.0 minor bump scheduled for the next release PR after this lands; the bump is justified because:

- New user-facing surface (seven new badge files per package).
- `run_pypinfo`'s return-type change is a public-ish API change at the Python level. The function isn't `_underscore`-prefixed; tests + future internal callers depend on its shape. v0.x leeway notwithstanding, this earns the minor bump.
- v1 hero file unchanged — no consumer breaks.

## Risks and open questions

- **Health-file size growth.** Each package goes from 2 fields to 3-with-7-key-map. For a typical four-package deploy, `_health.json` grows from ~500 bytes to ~2 KB. Negligible; surfaced for completeness.
- **Allowlist drift.** A future pypinfo emitting an unrecognized interactive installer (a hypothetical `pip3` or `mamba`) would not appear in any per-installer file or the v1 hero. Same fail-closed behavior as today; no v2-specific risk.
- **No open questions.** Chris signed off on Form A / absolute counts / B3 / C1 / README addendum. Color and config decisions made autonomously per the design's reasoning.
