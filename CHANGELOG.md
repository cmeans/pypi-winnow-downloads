# Changelog

## [Unreleased]

### Changed

- **`uv.lock`** transitive dependency pins refreshed via routine `uv lock --upgrade` resolve. Backstop for transitive bumps not yet picked up by Dependabot. No `pyproject.toml` range changes.

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-04-29

### Added

- **`.github/workflows/uv-lock-refresh.yml`** new scheduled workflow runs `uv lock --upgrade` every Thursday 12:00 UTC as a backstop for transitive dependency freshness — picks up minor/patch bumps that Dependabot's advisory- and cascade-driven flow hasn't yet surfaced. Skip-gate defers the run if a `dependencies` + `python`-labeled PR is already open (Dependabot mid-cycle or prior cron PR pending QA), so PRs don't overlap. Test gate (`uv sync --frozen --extra dev && uv run pytest`) blocks PR creation if the new lockfile breaks the suite. PR is opened via the existing `cmeans-claude-dev[bot]` App token (same path as `dependabot-changelog.yml`) so downstream CI checks (lint, typecheck, test, deploy-smoke) fire on the bot's push and don't leave the merge gate stuck. Most weeks: no PR (Dependabot already covered transitives via cascade). Spec: `docs/superpowers/specs/2026-04-29-uv-lock-refresh-cron-design.md`.

- **Per-OS badge files (v3 OS distribution feature).** The collector now emits three additional shields.io endpoint badge JSON files per package per window: `os-linux-<N>d-non-ci.json`, `os-macos-<N>d-non-ci.json`, `os-windows-<N>d-non-ci.json`. The badge label format mirrors v2's parameterized `(Nd)` style — e.g., `linux (30d)`, `macos (30d)`, `windows (30d)`. Color logic (`blue` if count ≥ 10 else `lightgrey`) is unchanged. Pypinfo group-by extends from `ci installer` to `ci installer system` so a single BigQuery call returns both per-installer and per-system breakdowns; BigQuery cost is unchanged (same source table, marginal column). `run_pypinfo()`'s return type changes from `dict[str, int]` to a TypedDict carrying `by_installer` and `by_system` aggregates. `_health.json` per-package successful entries gain a `counts_by_system` field. `PackageOutcome` gains a `counts_by_system` attribute. Filename slug and badge label use `macos` (user-friendly); the internal allowlist key is `Darwin` to match pypinfo's raw emission. No `pyproject.toml` range changes. The v0.2.0 hero-stability invariant is preserved: hero count remains `sum(by_installer.values())` regardless of system_name; per-system aggregation applies an independent allowlist filter so rows with missing or non-allowlisted system_name drop out of the per-OS aggregates but still count toward the hero. Backwards-compat: `downloads-<N>d-non-ci.json` and the seven `installer-*` files unchanged in filename, schema, and value for any given pypinfo response. README dogfood blocks gain a "By OS" paragraph parallel to the existing "By installer" paragraph; "What these badges actually count" gains a "By OS breakdown" paragraph; "Use this service for your own package" table grows three rows. Spec: `docs/superpowers/specs/2026-04-29-os-distribution-badge-design.md`.

### Changed

- **`uv.lock`** transitive dependency pins refreshed via routine `uv lock --upgrade` resolve. Backstop for transitive bumps not yet picked up by Dependabot. No `pyproject.toml` range changes.
- **`.gitignore`** ignores a private operator-tooling directory `.deploy/` at the repo root so maintainer-specific deploy scripts and design docs stay out of public history. The directory holds tooling like `update-collector.sh` (drives the CT 112 deployment via `WINNOW_REMOTE_RUN`) plus matching design / plan documents — parameterized in principle but maintainer-shaped in practice (SSH-to-Holodeck, `pct exec`, journald awareness). Other self-hosters can use plain `uv pip install --upgrade pypi-winnow-downloads`; this tooling does not need a public contract or maintenance burden. Rule is unanchored (`.deploy/`) to match the convention of the rest of the file (`.venv/`, `dist/`, `__pycache__/` etc. are all unanchored). Internal-only; no user-facing behavior change.

- **`.gitignore`** ignores `.claude/settings.local.json` — Claude Code's per-machine permission overrides. The file is created locally when a Claude Code session is granted machine-specific permissions (e.g., the project-scoped allow-list for read-only `ssh holodeck pct exec 112` commands added 2026-04-27 so future sessions can tail Caddy logs without prompts). The maintainer's global `~/.config/git/ignore` already covers this pattern, but adding the per-repo rule means anyone else cloning the repo who uses Claude Code without that global ignore won't see it as untracked either. Rule sits next to the new `.deploy/` block in a separate `# Per-machine Claude Code permission overrides` section. Internal-only; no user-facing behavior change.

## [0.2.0] - 2026-04-29

### Added

- **Per-installer badge files (v2 installer-mix feature).** The collector now emits seven additional shields.io endpoint badge JSON files per package per window, alongside the existing v1 hero (`downloads-<N>d-non-ci.json`, unchanged). New files: `installer-pip-<N>d-non-ci.json`, `installer-pipenv-<N>d-non-ci.json`, `installer-pipx-<N>d-non-ci.json`, `installer-uv-<N>d-non-ci.json`, `installer-poetry-<N>d-non-ci.json`, `installer-pdm-<N>d-non-ci.json`, and `installer-pip-family-<N>d-non-ci.json` (the pip-family aggregate = pip + pipenv + pipx). All seven apply the same `details.ci != True` filter as v1, with each file's `installer_name` allowlisting handled by the existing `_INSTALLER_ALLOWLIST`. The badge label format follows v1's parameterized `(Nd)` style — e.g., `pip (30d)`, `pip* (30d)`. Color logic (`blue` if count ≥ 10 else `lightgrey`) and the count-formatting helper (`format_count`) are unchanged. `run_pypinfo`'s return type changes from `int` to `dict[str, int]` mapping `installer_name` → count; the v1 hero count is now `sum(per_installer.values())`. `_health.json` per-package successful entries gain a `counts` field carrying the seven-keyed dict; the existing top-level `count` field is preserved verbatim for backwards compatibility with any monitoring or scripting that reads it. README expanded to dogfood all six individual installer counts in the badge row and gains a new "Use this service for your own package" section documenting the URL pattern for third-party packages. No new config fields — the collector always emits all eight files; maintainer's README picks which to display via shields.io endpoint URLs. Backwards-compat guarantees: `downloads-<N>d-non-ci.json` filename, schema, and value unchanged for any given pypinfo response; `_health.json` top-level fields unchanged. Spec: `docs/superpowers/specs/2026-04-28-installer-mix-badge-design.md`.

### Changed

- **README modernized for v2 — uv-first install + dogfood-row breakdown + per-installer narrative.** Coordinated documentation tweaks. (1) The hero badge stays in the top metadata row alongside PyPI version / Python versions / License / CI / Coverage so it's the first download signal a reader sees; below the description blockquote, a new `**By installer** (30d, non-CI):` paragraph stacks the six individual installer badges. The pip-family aggregate is documented in the [Use this service for your own package](#use-this-service-for-your-own-package) table only — kept out of the dogfood row to avoid stacking seven near-identical badges. (2) The `## What these badges actually count` section (renamed from `## What the badge actually counts`) gains a closing `**Per-installer breakdown.**` paragraph explaining that each individual badge applies the same `details.ci != True` filter as the hero — so they answer "non-CI downloads broken down by which packaging tool the user was running" — with `mcp-synology`'s observed uv-overtaking-pip shift cited as the kind of signal the breakdown is designed to surface. (3) Both install paths now lead with uv. The user-facing `## Install` section in `README.md` leads with `uv tool install pypi-winnow-downloads` (drops the `winnow-collect` console-script onto `PATH` in an isolated environment via [uv tool](https://docs.astral.sh/uv/concepts/tools/), no system-Python pollution), with plain `pip install pypi-winnow-downloads` as the no-uv fallback. The bare-systemd quick-start in `deploy/README.md` likewise switches its venv-at-`/opt/` walkthrough from `python3 -m venv` + `pip install` to `uv venv` + `uv pip install --python <venv>/bin/python`, with the inline note that `python3 -m venv` + plain pip remains a drop-in fallback for hosts without uv. `SECURITY.md`'s reporter-environment field gains the parallel `uv tool install` example so the "uv-first everywhere" framing isn't broken by an outlier. The pivot reflects this project's own tooling reality (uv.lock committed, dev workflow on `uv sync` / `uv run pytest` / `uv build`) plus the v2 data point that uv is becoming the dominant installer for some target packages — leading with `pip install` was a dogfooding miss.

- **Development status promoted from Alpha → Beta.** `pyproject.toml`'s `Development Status :: 3 - Alpha` classifier flips to `Development Status :: 4 - Beta`, and `README.md`'s `## Status` section now leads with "Beta as of v0.2.0" plus the deploy-since date and the explicit guarantee that the v1 hero badge JSON shape and filename are stable through 1.0. Trigger: four shipped releases (v0.1.0–v0.1.3), one minor (v0.2.0) about to ship, real production deploy running daily for days, 100% test coverage on `src/`, and additive-only schema evolution (v2 added new badge files alongside the unchanged hero rather than mutating any existing surface). Occasional breaking changes elsewhere in the 0.x series remain expected — the CHANGELOG `Changed` / `Removed` sections per release are the source of truth.

## [0.1.3] - 2026-04-28

### Added

- **`.github/workflows/publish.yml`** gains a `release` job that auto-creates a GitHub release page for every `v*` tag, with the release body extracted from the matching `## [X.Y.Z] - YYYY-MM-DD` section in `CHANGELOG.md`. The job runs after `publish` succeeds, so the release page appears only when the PyPI upload also lands. The `build` job extracts the section via a small `awk` script (reads from the matching `## [` heading until the next `## [` or `[link-ref]:` line, then trims leading and trailing blank lines) and fails the workflow before PyPI upload if the extracted body is empty — covering both the missing-section case and the heading-only case (a `## [X.Y.Z] -` line with no body underneath would otherwise pass a name-only presence check, ship to PyPI, and then leave the release job to fail with no PyPI rollback). The extracted `release_notes.md` rides through the workflow as an artifact so the same algorithm gates both ends, with no duplicated logic. Locally validated against v0.1.0 / v0.1.1 / v0.1.2. Pre-release tags (anything containing `-`, e.g., `v1.0.0-rc1`) get the `--prerelease` flag; stable tags rely on `gh release create`'s `--latest=auto` semver behavior. The job uses the workflow-default `GITHUB_TOKEN` with `permissions: contents: write` (no separate App token required). Backfilled v0.1.0 / v0.1.1 / v0.1.2 release pages remain in place; this only affects future tags.

### Fixed

- **`deploy/docker/Dockerfile`** uv pin bumped from `uv==0.4.*` to `'uv>=0.5,<1'`. The 0.4 series had drifted multiple minor releases behind current uv (0.5+, 0.6+) by the time the issue was filed, and the repo's `uv.lock` is generated by a current-series uv client — so `uv sync --frozen` inside the Docker build was running against a lock written by a newer client than the build's installed uv. Range pin (`>=0.5,<1`) lets the build pick up uv minor/patch updates within the 0.x major series automatically; cap at `<1` retains the major-bump gate. Range form was chosen over a tighter pin because Dependabot's `pip` ecosystem watches `pyproject.toml` only, not `RUN pip install` lines inside Dockerfiles ([dependabot/dependabot-core#2178](https://github.com/dependabot/dependabot-core/issues/2178)) — a tighter pin would silently rot the same way the 0.4 pin did. Verified end-to-end via the existing `deploy-smoke` CI job, which builds the multi-stage Dockerfile and asserts `winnow-collect --help` exits 0. Closes #34.

- **`.github/ISSUE_TEMPLATE/bug_report.yml`** version-field placeholder refactored from a literal version (`"0.1.0 or abc1234"`) to a format-hint (`"e.g., 0.1.x, or a commit SHA if testing main"`). The literal form claimed v0.1.0 was current and required a placeholder bump on every release; the hint form communicates the expected input shape (semver-series string OR commit SHA) without pinning to a specific shipped version, so it doesn't drift. Field-level guidance (`description: Output of pip show pypi-winnow-downloads or commit hash`) is unchanged. Closes #40.

- **README dogfood blockquote and hero-badge label note refreshed.** The hero blockquote (`README.md:16-19`) was authored before any release shipped: it claimed *"currently shows `0`"* and *"until the first release lands on PyPI; after that the count climbs automatically"*. Three releases later (v0.1.0 / v0.1.1 / v0.1.2) the live badge shows real traffic, and the README is `pyproject.toml`'s `long_description` so the stale framing was rendering on the PyPI project page too. Rewrote the blockquote to drop the snapshot-zero language and the future-tense framing — the live badge speaks for itself. Folded in finding #3 (replaced "milestone M3 deployment" — an internal milestone label readers don't recognize — with "v0.1.0 release", which is also more durable since v0.1.0 is the same date). Also added a small parenthetical to `README.md:23` clarifying that the parameterized `(Nd)` label resolves to `(30d)` in the reference deployment and is per-package configurable via `window_days`. No code, no other doc touched. Closes #43.

- **`.github/workflows/dependabot-changelog.yml`** subsection-insertion logic now respects Keep-a-Changelog v1.1.0 ordering (Added → Changed → Deprecated → Removed → Fixed → Security). Previously, when `## [Unreleased]` already had `### Added` (or any subsection that sorts after `### Changed`) but no `### Changed` block, the auto-CHANGELOG workflow inserted the new `### Changed` at `unreleased_idx + 1` regardless — producing out-of-order subsections (e.g., `### Changed` above `### Added`). Dormant on this repo until the v0.1.1 release, would have manifested on the next Dependabot bump after a release with only `### Added` in fresh Unreleased. The fix walks forward from `## Unreleased` to find either the first subsection that should sort AFTER `### Changed`, or the next `## ` release heading, and inserts before whichever comes first. Cascaded from the validated `cmeans/mcp-synology` PR #63 fix (squash 8a4df0d, merged 2026-04-26 23:24Z); upstream QA's algorithm-extraction smoke test against six KaC layouts (empty / Added-only / Changed-already / Added+Fixed / Fixed-only / bracketless) was reproduced locally on the cascaded fix — all six pass. Closes #26.

## [0.1.2] - 2026-04-27

### Fixed

- **CHANGELOG: three v0.1.1 entries recategorized from `### Fixed` to `### Added`.** PR #25 added new `### Added` and `### Changed` blocks at the top of the then-active `## [Unreleased]` section without repositioning entries from earlier PRs (#15, #22). PR #27 then inserted a `### Fixed` block between the existing `### Changed` and the orphans, leaving three additions visually attributed to the wrong subsection. v0.1.1 shipped with that miscategorization. This release moves the three orphans (Tailscale Funnel deploy alternative, README Acknowledgments + License sections, README Install pointer to pypinfo's GCP setup) under v0.1.1's `### Added` block where they belong by Keep-a-Changelog category. Documentation-only release; no code, dependency, or behavior change. Closes #28.

## [0.1.1] - 2026-04-26

### Added

- **`deploy/caddy/Caddyfile.example`** gains a global `log default` block writing server-level errors to `/var/log/caddy/error.log` (level `ERROR`, JSON, rotated `roll_size 50MiB` / `roll_keep 10` / `roll_keep_for 2160h` = 90 days) and a per-site access log at `/var/log/caddy/access.log` (JSON, rotated `roll_size 100MiB` / `roll_keep 14` / `roll_keep_for 720h` = 30 days). Replaces the single `log { output stdout }` stanza that buried request data inside `journalctl -u caddy` with no separate error-vs-access split and no rotation knobs. Caddy's built-in lumberjack handles rotation natively — no `logrotate` config required. Header comment documents a sharp gotcha discovered while rolling this out on the production deployment: running `caddy validate` against the Caddyfile *as root* pre-creates `/var/log/caddy/{error,access}.log` as `root:root 0600`, which the caddy daemon (running as user `caddy`) can't open on reload, leaving the systemd unit stuck in `reloading` state. Validate as the `caddy` user, or chown the log files before reloading. `deploy/README.md` "Pick an approach" table updated in the same PR — the Bare systemd row's pros now read "Collector logs to journal; Caddy logs to rotated files under `/var/log/caddy/`" instead of the previous "Native journal logging" claim, which became misleading once Caddy stopped writing to `journalctl -u caddy`.
- **`deploy-smoke` CI job** in `.github/workflows/ci.yml` exercises the four `deploy/` example artifacts that the Python-only matrix can't reach: builds the multi-stage Dockerfile, runs the container with overridden entrypoint to assert `winnow-collect --help` exits 0 (the bug class that took down PR #6 round 1 — venv installed in editable mode pointing at a non-existent `/src` so `import pypi_winnow_downloads` failed at startup), validates `deploy/docker/compose.yml.example` with `docker compose config` (`BADGE_HOST` substitution), and validates `deploy/caddy/Caddyfile.example` via `caddy validate` inside the official `caddy:2` image. Catches Dockerfile / compose / Caddyfile breakage before users hit it. Skips `systemd-analyze` on the timer because the referenced `.service` declares a binary at `/usr/local/bin/winnow-collect` that doesn't exist on a fresh CI runner. Closes #7.
- **`.github/PULL_REQUEST_TEMPLATE.md`** auto-fills new human-authored PRs with Summary, Test plan, and CHANGELOG sections matching this repo's CI commands (`uv run pytest --cov`, `uv run ruff check src/ tests/`, `uv run ruff format --check src/ tests/`, `uv run mypy src/pypi_winnow_downloads/`). Dependabot bypasses PR templates by design and is handled separately by the new auto-CHANGELOG workflow.
- **`.github/workflows/dependabot-changelog.yml`** auto-appends a `## [Unreleased]` → `### Changed` entry to Dependabot-authored PRs so they satisfy the per-PR CHANGELOG rule without manual intervention. Runs on `pull_request_target`, filters to `dependabot[bot]`, mints a GitHub App installation token via `actions/create-github-app-token`, fetches metadata via `dependabot/fetch-metadata@v3.1.0` (the v3 line fixed empty `prevVersion`/`newVersion` on grouped PRs), and pushes the CHANGELOG commit under the `cmeans-claude-dev[bot]` identity. The App-token push is the load-bearing piece: `secrets.GITHUB_TOKEN`-authored pushes do NOT re-trigger required `pull_request` checks (lint, typecheck, test) under GitHub's anti-loop policy, which would leave Dependabot PRs un-mergeable under the `main-protection` ruleset's required-status-checks rule. Loop guard skips when the last commit is already by the bot; idempotency guard skips when the PR number is already referenced in `CHANGELOG.md`. Operator must configure two repo secrets (`BOT_APP_ID`, `BOT_APP_PRIVATE_KEY`) before the workflow can run. Validated end-to-end on `cmeans/mcp-synology` (PRs #57 + #58 + #60 + #61, the latter being live verification on a real grouped Dependabot bump). Cross-repo playbook lives in awareness `dependabot-pr-hygiene-playbook`.
- `deploy/README.md` gains an `## Alternative HTTPS exposure:
  Tailscale Funnel` section documenting [Tailscale
  Funnel](https://tailscale.com/kb/1223/funnel) as a drop-in
  replacement for the public-HTTPS layer (Caddy + Let's Encrypt +
  DDNS + router port-forward). Free Personal-tier eligible; useful
  for self-hosters behind CGNAT, on residential IPs that rotate, or
  who'd rather not expose a home IP in public DNS. Documents the
  trade-offs (`<device>.<tailnet>.ts.net` URL form locked to the
  tailnet on the free plan; allowed public ports 443 / 8443 /
  10000; non-configurable bandwidth limits) and ships a
  five-command setup against `bare-systemd` runtime: install
  tailscale, serve `output_dir` on `127.0.0.1:8443` via
  `systemd-run`, `tailscale funnel --bg`, discover the URL, smoke
  check. Cross-referenced from the **Pick an approach** section so
  it's discoverable without reading the whole doc end-to-end. No
  in-tree files specific to Funnel.
- README gains `## Acknowledgments` (pypinfo, shields.io, the
  `bigquery-public-data.pypi.file_downloads` dataset, plus a
  development-collaboration credit to Claude Code) and `## License`
  sections, plus a `© 2026 Chris Means` line. The repo has shipped
  Apache 2.0 from day one (declared in `pyproject.toml` and `LICENSE`);
  this just surfaces attribution and license at the README's footer
  where readers expect it. Cross-file links use absolute GitHub URLs
  so they don't 404 on the PyPI project page (the README is also
  `pyproject.toml`'s `long_description`).
- README's `## Install` section now points new users at pypinfo's
  installation guide for the GCP credential setup (create a project,
  enable the BigQuery API, generate the service-account JSON), since
  every install needs that JSON before `winnow-collect` will run.
  Avoids reproducing pypinfo's 18-step walkthrough here while still
  closing the obvious onboarding gap.

### Changed

- **Bump docker group: python 3.13-slim→3.14-slim** (#24)
- **Bump github-actions group: codecov/codecov-action 5→6** (#23)
- **`.github/dependabot.yml`** commit-message prefix changed from `"chore(deps)"` to `"chore"` across all three ecosystems (pip, github-actions, docker). Combined with the existing `include: "scope"` setting, this restores the canonical Dependabot title format `chore(deps): bump <pkg>` instead of the doubled `chore(deps)(deps): bump <pkg>` produced by the previous config (Dependabot auto-appends `(deps)` when `include: scope` is set, so the prefix must be bare). Surfaced live on PRs #23 and #24, which exhibited the doubled prefix.

### Fixed

- **Coverage on `src/` reaches 100%; `fail_under = 100` gate added in `pyproject.toml`.** Five previously-uncovered defensive lines now have real tests, no `# pragma: no cover` annotations, no `coverage_exclude_lines` patterns. Specifically: `__init__.py:7-8` (`PackageNotFoundError` fallback) covered by a `monkeypatch + importlib.reload` test; `__main__.py:52` (the `if __name__ == "__main__": main()` guard) covered by a `runpy.run_module(..., run_name="__main__")` test that stubs `collector.collect` to a no-op so the line runs without shelling out to pypinfo; `collector.py:190` (non-integer `download_count` defensive raise) covered by feeding the runner a row with a string download_count; `config.py:42` (non-mapping `service:` value) covered by `service: just-a-string` YAML; `config.py:86` (non-list `packages:` value) covered by `packages: 42` YAML. Adds `[tool.coverage.run] source = ["src/pypi_winnow_downloads"]` and `[tool.coverage.report] fail_under = 100, show_missing = true` so future regressions trip CI immediately. Total tests: 71 (was 66). Closes #37.
- **collector: `service.stale_threshold_days` is now actually consulted.** `config.example.yaml` documented "warn (in the log) if the last successful collector run is older than this many days" but no caller read the field — it was loaded, validated, and silently ignored. `collect()` now calls a new `_check_staleness(output_dir, threshold_days, now)` helper at the start of each run that reads the previous `_health.json`, parses its `finished` timestamp, and emits `logger.warning("collector: previous successful run is %.1f days old (threshold: %d days); previous finished: %s", ...)` when the gap exceeds the threshold. The check is log-only (does NOT mutate badge JSON, per the documented v1 contract) and degrades silently when the previous health file is absent (first run / fresh deploy), unreadable, malformed, missing the `finished` field, or shows a future timestamp (clock skew). Seven regression tests cover: warn-when-stale, silent-when-fresh, silent-on-no-previous-health, silent-on-malformed-json, silent-on-future-timestamp, silent-on-unreadable-previous-health (OSError other than `FileNotFoundError` — exercised by creating `_health.json` as a directory so `Path.read_text` raises `IsADirectoryError`), and silent-on-missing-`finished`-key (independent branch coverage of the `KeyError` arm of the JSON-parse `except` union). Both new silent-* tests assert on the documented DEBUG-log records, locking in the operator-visible signal that distinguishes the failure modes. Closes #33.
- **collector: `_write_health` `OSError` no longer escapes per-package isolation.** A failure inside the health-file write step (disk full, output dir not writable, atomic-replace cross-device, etc.) used to propagate as an unhandled `OSError` traceback through `__main__.main()`, bypassing the structured `winnow-collect: N package(s) failed: …` exit message and producing a raw exit. The fix wraps `_write_health(...)` inside `collect()` with `try/except OSError`, logs the failure, and surfaces it via a new `CollectorResult.health_write_error: str | None` field (default `None`, backward-compat). `__main__.main()` now combines per-package failures and health-write failures into one structured exit message (`winnow-collect: 2 package(s) failed: foo, bar; health file write failed: [Errno 28] No space left on device`). Adds `test_collect_health_write_oserror_recorded_not_raised` (monkeypatches `os.replace` to raise `ENOSPC` only on the health file) and `test_main_combines_package_and_health_failure_messages` for regression coverage. Closes #32.
- `README.md` line 11: canonicalized the [shields.io](https://shields.io/badges/endpoint-badge) doc link to match the form already used at line 96. Both references now point at the same canonical URL instead of relying on `/endpoint` redirecting to `/badges/endpoint-badge`. Closes #16.

## [0.1.0] - 2026-04-24

### Changed

- **README closing line retired.** The bare `Pre-alpha. Not yet usable.`
  was honest while the service was unbuilt; it became misleading after
  the M3 deployment went live. Replaced with two short sections —
  `## Install` (a `pip install` + `winnow-collect --config <path>`
  walkthrough plus a pointer to `deploy/README.md` for the systemd +
  Caddy reference deployment) and `## Status` (Alpha; reference
  deployment running at `pypi-badges.intfar.com`; expect rough edges in
  the 0.x series). The README is `pyproject.toml`'s `long_description`,
  so it doubles as the PyPI project page — the new sections use
  absolute GitHub URLs for cross-file links so they don't 404 on PyPI.
- **Hero metric definition tightened.** The badge now counts only downloads
  whose `details.installer.name` is one of `pip`, `uv`, `poetry`, `pdm`,
  `pipenv`, or `pipx` (the interactive Python packaging-tool family) — in
  addition to the existing `details.ci != True` filter. Mirror traffic
  (`bandersnatch`, `Nexus`, `devpi`, `Artifactory`, `z3c.pypimirror`),
  browser fetches via the PyPI web UI, generic HTTP UAs (`requests`, `curl`),
  and uncategorised installer rows are now excluded. **This is a breaking
  change to the metric**: badge values for any deployed instance will drop
  on next collector run (often substantially — for one v1 seed package
  bandersnatch alone accounted for 48% of the previous count). The filter
  is **fail-closed**: a future pypinfo emitting a new installer name will
  be excluded until the allowlist in `collector.py` is updated explicitly.
- **Badge label** changed from `downloads (Nd, non-CI)` to
  `pip*/uv/poetry/pdm (Nd)` to make the new filter visible at the badge
  surface (the asterisk on `pip*` denotes the pip-derived family — pip
  itself plus pipenv and pipx). Output filename
  (`<pkg>/downloads-Nd-non-ci.json`) is unchanged so existing endpoint
  URLs continue to resolve.
- `run_pypinfo` argv now pivots by both `ci` AND `installer` (was just
  `ci`); JSON rows gain an `installer_name` field that the parser uses
  for the allowlist filter. Missing `installer_name` raises
  `CollectorError` (loud schema-break detection).
- **`pypinfo` resolved by absolute path, not PATH lookup.** The
  collector now constructs argv[0] as
  `Path(sys.executable).parent / "pypinfo"` via the new
  `_resolve_pypinfo_path()` helper. pypinfo is a runtime dependency, so
  its console script is installed alongside the running interpreter
  regardless of layout (venv, system pip, pip --user, pipx isolated
  venv, docker). Removes the dependency on `subprocess.run` finding
  `pypinfo` via PATH, which was install-layout-fragile (notably broken
  under systemd's stripped PATH at M3 deploy time). The `Environment=PATH=`
  directive in `deploy/systemd/*.service` and the parallel `pypinfo`
  symlink step in `deploy/README.md` are no longer required and have
  been removed.

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
  invokes `pypinfo --json --days <N> --all <pkg> ci` and passes the
  service-account credential via the `GOOGLE_APPLICATION_CREDENTIALS` env
  var (pypinfo's `core.py` reads it on the no-flag path; passing
  `-a/--auth` on the command line short-circuits pypinfo to a
  credential-setter mode and would prevent the query from running).
  `XDG_DATA_HOME` is also redirected to a per-invocation
  `tempfile.TemporaryDirectory` so pypinfo's persisted-credential TinyDB
  (`platformdirs.user_data_dir('pypinfo')/db.json`, which would otherwise
  take priority over the env var) starts empty for every run. `run_pypinfo`
  parses the JSON `rows` and sums `download_count` across rows where
  `ci != "True"`. `collect(config)` iterates the configured packages,
  writes one shields.io endpoint JSON per package at
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
- `deploy/` directory with example deployment artifacts (no Chris-specific
  paths). `deploy/README.md` compares three approaches (bare systemd,
  Docker host-scheduled, Docker Compose) with quick-start instructions
  for each. `deploy/systemd/` ships a `Type=oneshot` service unit (with
  hardening directives — `ProtectSystem=strict`, `RestrictAddressFamilies`,
  `PrivateTmp`, etc.) and a daily timer with `RandomizedDelaySec=30m` and
  `Persistent=true`. `deploy/caddy/Caddyfile.example` serves the output
  directory over HTTPS via Let's Encrypt automatic provisioning, with
  CORS + `Cache-Control: public, max-age=3600` for the badge JSON.
  `deploy/docker/Dockerfile` is a multi-stage build (uv
  `sync --frozen --no-dev --no-editable` against the committed lockfile;
  `--no-editable` is load-bearing because uv's default editable install
  embeds `/src/src` into a `.pth` file, which dangles in the runtime
  stage after `COPY --from=build`). The runtime stage runs as a non-root
  `winnow` user. `deploy/docker/compose.yml.example` pairs the collector
  (one-shot, `run-once` profile) with Caddy (long-running) sharing a
  named volume; host scheduling drives the collector since Compose has
  no native scheduler.

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
- `run_pypinfo` redirects `XDG_DATA_HOME` to a per-invocation
  `tempfile.TemporaryDirectory` so pypinfo's `get_credentials()`
  (`db.py:23-26` via `cli.py:171`, with `core.py:56` falling back via
  `creds_file or os.environ.get(...)`) cannot let a persisted-credential
  TinyDB at `platformdirs.user_data_dir('pypinfo')/db.json` take priority
  over `GOOGLE_APPLICATION_CREDENTIALS`. Without this, on any host where
  `pypinfo -a <path>` had been run manually (a developer workstation, a
  shared box), the env var would be silently ignored and a stale persisted
  path would be used. Tests gain an integration test that pre-populates a
  polluted DB at the test process's `XDG_DATA_HOME` and asserts the env
  var still wins — exercising pypinfo's actual priority order, not just
  env transmission.
- README's dogfood badge URL pointed at `downloads-30d.json`, but the
  collector writes `downloads-30d-non-ci.json` (per
  `_BADGE_FILENAME_TEMPLATE` in `collector.py`). After the M3 deploy went
  live, shields.io 404'd and rendered "custom badge: resource not found"
  instead of the actual count. URL now matches the live filename. The
  dogfood-note prose was also refreshed: it previously said "shields.io
  renders an error state, which is the correct signal for a pre-v1
  project" — accurate while the deploy was pending, stale after M3 ship;
  the new prose reflects deploy-live + pre-PyPI state (badge currently
  shows `0`).
- `deploy/systemd/pypi-winnow-downloads-collector.service` did not set
  `PATH=`, so when the collector spawned `pypinfo` via `subprocess.run`,
  systemd's inherited PATH (`/sbin:/bin:/usr/sbin:/usr/bin`) did not
  include the venv's bin and the call failed at runtime — every package
  recorded as a `CollectorError`. The example unit now sets
  `Environment=PATH=/opt/pypi-winnow-downloads/bin:/usr/local/bin:/usr/bin:/bin`
  with a comment block explaining why and how to adjust if the install
  prefix differs. Caught at first deploy on CT 112; CI didn't catch it
  because the existing checks all run at the Python level.
- `deploy/README.md`'s install steps only symlinked `winnow-collect` into
  `/usr/local/bin/`; `pypinfo` was missing, so even with PATH inherited
  correctly the collector's subprocess for pypinfo wouldn't resolve.
  Steps now use the venv-at-/opt pattern explicitly with a
  `winnow-collect` symlink — pypinfo's symlink is no longer required as
  of the resolver-based pypinfo lookup landed in this release (see the
  "pypinfo resolved by absolute path" Changed entry above); the
  collector finds pypinfo via `sys.executable`'s neighbor instead of
  PATH.

[Unreleased]: https://github.com/cmeans/pypi-winnow-downloads/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/cmeans/pypi-winnow-downloads/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/cmeans/pypi-winnow-downloads/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/cmeans/pypi-winnow-downloads/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/cmeans/pypi-winnow-downloads/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/cmeans/pypi-winnow-downloads/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/cmeans/pypi-winnow-downloads/releases/tag/v0.1.0
