# OS distribution badges (v3 feature)

**Status:** Draft, brainstorming-approved 2026-04-29
**Goal:** Add per-OS download breakdown badges (Linux / macOS / Windows) parallel to the per-installer breakdown shipped in v0.2.0.
**Spec author:** Claude
**Target release:** v0.3.0 (minor bump — additive feature, no breaking changes)

## Why

The installer-mix v2 feature surfaces *which packaging tool* users run when they install a package. The OS distribution breakdown answers a different operator question: *what platforms is this used on?* For a maintainer deciding what OS matrix to test against, what platform-specific bugs to prioritize, or whether to ship a wheel for a specific OS, the OS breakdown is more decision-useful than the installer breakdown.

Same shape as installer-mix: one cron run per day, three new shields.io endpoint JSON files per package per window, dogfood layout extended to surface them on the README.

## Architecture

Mirrors the v2 installer-mix feature one axis over. Code reuse is high; the new dimension shares the same allowlist-filter + per-key file-emission + parameterized-label patterns.

| Aspect | v2 installer-mix | v3 OS distribution |
| --- | --- | --- |
| Pypinfo group-by axis | `installer` | `system` |
| Allowlist key (matches pypinfo emission) | `pip`, `pipenv`, `pipx`, `uv`, `poetry`, `pdm` | `Linux`, `Darwin`, `Windows` |
| Filename slug | `installer-pip-Nd-non-ci.json` × 7 | `os-linux-Nd-non-ci.json` × 3 |
| Public label | `pip (30d)` etc. | `linux (30d)` / `macos (30d)` / `windows (30d)` |
| Family aggregate | pip-family (pip + pipenv + pipx) | none |
| Hero impact | none | none (hero filter unchanged — see "Hero count semantics") |

The collector remains a one-shot daily run; nothing about scheduling, output layout, or HTTPS exposure changes.

## Data path

### Pypinfo invocation

`run_pypinfo()` adds one positional arg to its argv: `["ci", "installer"]` becomes `["ci", "installer", "system"]`. Pypinfo passes this to BigQuery as a multi-dimensional GROUP BY. The cartesian row count goes from ~6 (installer-only) to ~18 (installer × system after allowlist filtering). BigQuery's pricing is by bytes scanned, not row count, and the additional column (`details.system.name`) is on the same source table, so the marginal cost is negligible.

### Return shape

`run_pypinfo()` return type changes from `dict[str, int]` (installer→count) to a structured dict:

```python
{
    "by_installer": {"pip": int, "pipenv": int, "pipx": int, "uv": int, "poetry": int, "pdm": int},
    "by_system":    {"Linux": int, "Darwin": int, "Windows": int},
}
```

Hero count is `sum(by_installer.values())`, unchanged. `pip-family` derived value (`pip + pipenv + pipx`) is still computed downstream in the badge-emission step, not in `run_pypinfo()`.

### Row aggregation

For each pypinfo row:
1. If `installer ∈ _INSTALLER_ALLOWLIST`, increment `by_installer[installer]`.
2. If `system ∈ _SYSTEM_ALLOWLIST`, increment `by_system[system]`.

The two checks are independent — a row can contribute to one, the other, both, or neither. Rows where ci is `True` are dropped before either check runs (existing behavior, unchanged).

### Hero count semantics

The v0.2.0 release promised "v1 hero badge JSON shape and filename are stable through 1.0." Adding a system-name filter to the hero would shift counts (rows with allowlisted installer + null/non-allowlisted system would drop out). To honor the v0.2.0 contract:

- **Hero count formula unchanged.** Hero = sum across rows where `installer ∈ _INSTALLER_ALLOWLIST`, regardless of `system`.
- **Per-OS badges sum to ≤ hero.** The gap = rows with allowlisted installer + non-allowlisted/null system. Documented analogously to the per-installer-sum ≤ hero gap.
- **Per-installer badges sum to ≤ hero.** Same v0.2.0 behavior, unchanged.

### Data availability and "backfill"

There is no special backfill action: pypinfo's BigQuery query returns whatever rolling window we request (`--days 30` = last 30 days), regardless of when the collector code shipped. BigQuery's `bigquery-public-data.pypi.file_downloads` table has had `details.system.name` populated for years.

On the first post-merge collector run for any package, the per-OS badges reflect 30 days of history. For `pypi-winnow-downloads` itself (~5 days of data) the badges will look thin. For mature dogfood packages (`mcp-clipboard`, `mcp-synology`) the badges populate immediately with a full 30-day window.

## Badge files

Three new shields.io endpoint JSON files per package per window, alongside the unchanged 8 files from v0.2.0:

- `os-linux-{N}d-non-ci.json` — label `linux (Nd)`
- `os-macos-{N}d-non-ci.json` — label `macos (Nd)` (filename and label use the user-friendly form; the allowlist key is `Darwin` to match pypinfo's emission)
- `os-windows-{N}d-non-ci.json` — label `windows (Nd)`

Color logic reuses the existing `format_count` and color helpers: `blue` if count ≥ 10 else `lightgrey`. No new helpers needed.

Total badge files per package per window goes from 8 to 11. Existing 8 unchanged in filename, schema, or value for any given pypinfo response.

## `_health.json` shape

Per-package successful entries gain one new field:

```json
{
  ...,
  "count": <hero count>,
  "counts": {"pip": ..., "uv": ..., ...},
  "counts_by_system": {"Linux": ..., "Darwin": ..., "Windows": ...}
}
```

`count` and `counts` are preserved verbatim for backwards compat with any monitoring or scripting that reads them. No joint `(installer × system)` matrix field — YAGNI.

Top-level `_health.json` fields (`finished`, `started`, etc.) unchanged.

## Configuration

No new config knobs. Always-on, same as installer-mix v2. The collector emits all 11 files per package per window; the maintainer's README picks which to display via shields.io endpoint URLs. Other self-hosters get the same files automatically.

## README impact

### Dogfood block

Each package's dogfood block gets a new paragraph under the existing "By installer" paragraph:

```markdown
**By installer (30d, non-CI):** [pip] [pipenv] [pipx] [uv] [poetry] [pdm]

**By OS (30d, non-CI):** [linux] [macos] [windows]
```

Parallel structure to the v0.2.0 layout. Three new badges per package; no other layout changes.

### "What these badges actually count" section

Gains one closing paragraph after the existing "Per-installer breakdown" paragraph:

> **By OS breakdown.** Each per-OS badge applies the same `details.ci != True` filter as the hero — they answer "non-CI downloads on that OS." `Darwin` is the pypinfo emission for what users call macOS; the badge filename and label use `macos`. The per-OS sum can be less than the hero count: rows whose user-agent didn't expose a system_name (or exposed one outside Linux/Darwin/Windows) drop out of the per-OS aggregation but still count toward the hero.

### "Use this service for your own package" table

Gains 3 new rows for the new endpoint URLs (linux/macos/windows), parallel to the existing per-installer rows.

## Out of scope (explicit)

- No "OS family" aggregate (no analog to pip-family).
- No tightening of v1 hero count.
- No new config knobs (always-on, like installer-mix v2).
- No multi-package OS aggregation badge.
- No deprecation of the installer feature.
- No joint-matrix field in `_health.json`.

## Acceptance criteria

- Collector emits 3 new badge files per package per window with shields.io endpoint shape (`label`, `message`, `color`, `schemaVersion`, `cacheSeconds` matching existing helpers).
- Existing 8 files (hero + 7 installer-mix) unchanged in filename, schema, and value for any given pypinfo response.
- `_health.json` per-package successful entries gain `counts_by_system`; existing fields preserved verbatim.
- README dogfood block grows a "By OS" paragraph; "What these badges actually count" gains a per-OS breakdown paragraph; "Use this service for your own package" table gains 3 new rows.
- Tests cover: row aggregation including the (allowlisted-installer + non-allowlisted-system) edge case that's intentionally dropped from per-OS but kept in hero; badge file emission for all 3 new files; `_health.json` shape; README live-render check (parallel to existing dogfood live-render checks).
- `## [Unreleased]` → `### Added` bullet describing the new files and the data-semantics gap.

## Release framing

v0.3.0 — minor bump per SemVer. Additive: 3 new badge files, 1 new `_health.json` field. No breaking changes to v0.2.0 contracts.

## Implementation file list

- Modify: `src/pypi_winnow_downloads/collector.py` — add `_SYSTEM_NAMES`, `_SYSTEM_ALLOWLIST`, `_OS_BADGE_SPECS`; change pypinfo argv from `["ci", "installer"]` to `["ci", "installer", "system"]`; restructure `run_pypinfo()` return shape; extend the row-aggregation loop with the per-system increment; extend the badge-emission loop with the 3 new files; extend `_write_health()` to include `counts_by_system`.
- Modify: `tests/test_collector.py` — extend existing tests for the new return shape, the new dimension, the v0.2.0 hero-stability invariant, and the (allowlisted-installer + non-allowlisted-system) edge case.
- Modify: `README.md` — add "By OS" paragraph to dogfood block; add "By OS breakdown" paragraph; add 3 rows to the "Use this service for your own package" table.
- Modify: `CHANGELOG.md` — `## [Unreleased]` → `### Added` bullet.
- Bump: `pyproject.toml` `version` from `0.2.0` to `0.3.0` at release time (separate release PR, not part of the feature PR).
