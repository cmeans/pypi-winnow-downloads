# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

[Unreleased]: https://github.com/cmeans/pypi-winnow-downloads/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/cmeans/pypi-winnow-downloads/releases/tag/v0.1.0
