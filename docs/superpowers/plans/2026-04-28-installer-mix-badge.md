# Installer-Mix Badge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-package emission of seven additional shields.io endpoint badge JSON files (six individual installers in the v1 allowlist + a `pip-family` aggregate), v1 hero kept side-by-side, README updated to dogfood the breakdown and document the URL pattern for third-party packages.

**Architecture:** v1's `run_pypinfo` already pivots by `installer_name` (since v0.1.0 — argv passes both `ci` and `installer` as fields) but sums all six allowlisted installers into one int. v2 stops summing: `run_pypinfo` returns a `dict[str, int]` mapping installer name → count. `collect()` writes the existing v1 hero file unchanged plus seven per-installer files. The health file additively gains a `counts` map per package. No new BigQuery queries, no extra subprocess invocations. Straight-line code in `_collect_one`; refactor to a generator-list abstraction is explicitly deferred — YAGNI until v2 grows another badge family.

**Tech Stack:** Python 3.11+, hatchling, pytest + ruff + mypy, uv. Existing modules: `src/pypi_winnow_downloads/collector.py` (the only behavior change), `src/pypi_winnow_downloads/badge.py` (no change), `src/pypi_winnow_downloads/__main__.py` (no change), `tests/test_collector.py` (most test churn).

**Spec:** `docs/superpowers/specs/2026-04-28-installer-mix-badge-design.md`. All design decisions trace to the spec — read it first.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/pypi_winnow_downloads/collector.py` | Modify | `run_pypinfo` returns dict, `_collect_one` writes 8 badges + per-installer counts on outcome, `_write_health` includes counts map. New module-level constants for ordering and per-installer badge specs. |
| `src/pypi_winnow_downloads/badge.py` | No change | shields.io endpoint shape unchanged. |
| `src/pypi_winnow_downloads/__main__.py` | No change | CLI surface unchanged. |
| `tests/test_collector.py` | Modify | Adapt 7 existing tests asserting on `int` return; add 6 new tests per spec test list. |
| `README.md` | Modify | Dogfood badge row expanded with 6 individual installer badges; new `## Use this service for your own package` section between `## Install` and `## Status`. |
| `CHANGELOG.md` | Modify | One `### Added` entry under `[Unreleased]` describing all of the above. |

No new files. No abstraction layer added (per spec's YAGNI guidance).

---

## Task 1: `run_pypinfo` returns `dict[str, int]` instead of `int`

**Files:**
- Modify: `src/pypi_winnow_downloads/collector.py:25-194` (constants + `run_pypinfo`)
- Test: `tests/test_collector.py` (add 2 new tests, adapt 7 existing)

The signature change ripples to every existing test that calls `run_pypinfo(...)` and assigns to `count`. Those 7 tests assert one of: a specific int (`assert count == 100`), zero (`assert count == 0`), or a sum-equivalent assertion. Adapt each to assert against either `sum(result.values())` (when the test was about totaling) or specific dict shape (when the test cared about which installers contributed).

- [ ] **Step 1: Add `_INSTALLER_NAMES` ordered tuple alongside `_INSTALLER_ALLOWLIST`**

Modify `src/pypi_winnow_downloads/collector.py:42`. Replace the existing `_INSTALLER_ALLOWLIST` line with:

```python
# Ordering matters: dicts returned by run_pypinfo iterate in this order, which
# the per-installer badge writer relies on for deterministic output and tests
# assert against. Allowlist keeps the same membership; tuple gives us order.
_INSTALLER_NAMES: tuple[str, ...] = ("pip", "pipenv", "pipx", "uv", "poetry", "pdm")
_INSTALLER_ALLOWLIST: frozenset[str] = frozenset(_INSTALLER_NAMES)
```

- [ ] **Step 2: Write the failing test for dict return**

Add to `tests/test_collector.py` after `test_run_pypinfo_filters_out_non_allowlisted_installers` (around line 287):

```python
def test_run_pypinfo_returns_per_installer_dict(tmp_path: Path) -> None:
    creds = tmp_path / "key.json"
    creds.write_text("{}")

    rows = [
        {"installer_name": "pip", "ci": "False", "download_count": 50},
        {"installer_name": "pipenv", "ci": "False", "download_count": 1},
        {"installer_name": "pipx", "ci": "False", "download_count": 2},
        {"installer_name": "uv", "ci": "False", "download_count": 60},
        {"installer_name": "poetry", "ci": "False", "download_count": 11},
        {"installer_name": "pdm", "ci": "False", "download_count": 3},
        {"installer_name": "bandersnatch", "ci": "False", "download_count": 999},  # excluded by allowlist
        {"installer_name": "pip", "ci": "True", "download_count": 1000},  # excluded by CI filter
    ]

    def fake_runner(argv: Sequence[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(argv), returncode=0, stdout=json.dumps({"rows": rows}), stderr=""
        )

    result = run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)

    assert result == {"pip": 50, "pipenv": 1, "pipx": 2, "uv": 60, "poetry": 11, "pdm": 3}


def test_run_pypinfo_zeroes_installers_with_no_rows(tmp_path: Path) -> None:
    creds = tmp_path / "key.json"
    creds.write_text("{}")

    rows = [
        {"installer_name": "pip", "ci": "False", "download_count": 100},
    ]

    def fake_runner(argv: Sequence[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(argv), returncode=0, stdout=json.dumps({"rows": rows}), stderr=""
        )

    result = run_pypinfo("solopkg", 30, credential_file=creds, runner=fake_runner)

    assert result == {"pip": 100, "pipenv": 0, "pipx": 0, "uv": 0, "poetry": 0, "pdm": 0}
```

- [ ] **Step 3: Run new tests — verify FAIL**

```bash
cd /home/cmeans/.claude/worktrees/pypi-winnow-downloads-installer-mix
uv run pytest tests/test_collector.py::test_run_pypinfo_returns_per_installer_dict tests/test_collector.py::test_run_pypinfo_zeroes_installers_with_no_rows -v
```

Expected: both FAIL with `AssertionError` — `run_pypinfo` returns an int, not a dict. The assertion `result == {...}` will fail with the int value on the LHS.

- [ ] **Step 4: Modify `run_pypinfo` to return per-installer dict**

In `src/pypi_winnow_downloads/collector.py`, change the function signature and the body. Replace lines 110-194 (the entire `run_pypinfo` function) with:

```python
def run_pypinfo(
    package: str,
    window_days: int,
    *,
    credential_file: Path,
    runner: Runner = _default_runner,
) -> dict[str, int]:
    # Note: do NOT pass `-a/--auth <path>` on argv. pypinfo (cli.py:130-133)
    # short-circuits to a credential-setter path when --auth is present and
    # never runs the query. Use GOOGLE_APPLICATION_CREDENTIALS instead, which
    # pypinfo's core.py reads via os.environ.get on the no-flag path.
    argv = [
        _resolve_pypinfo_path(),
        "--json",
        "--days",
        str(window_days),
        "--all",
        package,
        "ci",
        "installer",
    ]

    # XDG_DATA_HOME isolation: pypinfo's get_credentials() (db.py:23-26 via
    # cli.py:171) reads a persisted credential path from
    # `platformdirs.user_data_dir('pypinfo')/db.json` and returns it from
    # `creds_file or os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')`
    # (core.py:56) — left-to-right `or` means a persisted path wins and the
    # env var is silently ignored. On any host where `pypinfo -a <path>` has
    # been run manually, that's a foot-gun. Pointing XDG_DATA_HOME at a
    # fresh empty dir per invocation makes pypinfo's TinyDB query return
    # None so the env-var fallback supplies the credential.
    with tempfile.TemporaryDirectory(prefix="pypi-winnow-pypinfo-state-") as state_dir:
        env = {
            **os.environ,
            "GOOGLE_APPLICATION_CREDENTIALS": str(credential_file),
            "XDG_DATA_HOME": state_dir,
        }

        try:
            result = runner(argv, env)
        except subprocess.TimeoutExpired as e:
            raise CollectorError(f"pypinfo timed out for {package!r} after {e.timeout}s") from e

    if result.returncode != 0:
        raise CollectorError(
            f"pypinfo exited {result.returncode} for {package!r}: {result.stderr.strip()}"
        )
    try:
        payload: Any = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise CollectorError(f"pypinfo produced malformed JSON for {package!r}: {e}") from e

    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise CollectorError(f"pypinfo output missing 'rows' list for {package!r}")

    # Initialize counts to 0 for every allowlisted installer so the returned
    # dict shape is stable regardless of which installers had rows in this
    # window. Order follows _INSTALLER_NAMES so callers can rely on iteration
    # order for badge filenames and tests can assert on equality with a
    # specific dict literal.
    counts: dict[str, int] = {name: 0 for name in _INSTALLER_NAMES}
    for row in rows:
        if not isinstance(row, dict):
            raise CollectorError(
                f"pypinfo row for {package!r} has unexpected shape (not a dict): {row!r}"
            )
        # pypinfo emits ci as the *string* "True" / "False" / "None" — BigQuery
        # cell values are passed through str() in pypinfo's parse_query_result.
        # If a future pypinfo version emits a native bool/None instead, this
        # comparison would silently flip and start counting CI traffic as
        # non-CI; the non-dict-row guard above catches schema breaks loudly.
        if row.get("ci") == "True":
            continue
        # installer_name is required when we pivot by `installer`; missing
        # the column means pypinfo's schema changed under us and we should
        # fail loudly rather than silently undercount.
        if "installer_name" not in row:
            raise CollectorError(
                f"pypinfo row for {package!r} missing 'installer_name' field: {row!r}"
            )
        installer = row["installer_name"]
        if installer not in _INSTALLER_ALLOWLIST:
            continue
        count = row.get("download_count", 0)
        if not isinstance(count, int):
            raise CollectorError(
                f"pypinfo row for {package!r} has non-integer download_count: {count!r}"
            )
        counts[installer] += count
    return counts
```

- [ ] **Step 5: Run the two new tests — verify PASS**

```bash
uv run pytest tests/test_collector.py::test_run_pypinfo_returns_per_installer_dict tests/test_collector.py::test_run_pypinfo_zeroes_installers_with_no_rows -v
```

Expected: both PASS.

- [ ] **Step 6: Find and adapt existing tests asserting `int` return**

Find the assignments that capture the v1 int:

```bash
grep -n 'count = run_pypinfo' tests/test_collector.py
```

Expected matches around lines 138, 215, 242, 284, 315, 344, 380. Each asserts on `count` later. Adapt each:

- Tests asserting `assert count == N` for some non-zero `N` change to `assert sum(result.values()) == N` (rename the local from `count` to `result` to keep semantics legible).
- Tests asserting `assert count == 0` change to `assert sum(result.values()) == 0` likewise.

Concrete examples:

`test_run_pypinfo_sums_non_ci_rows_and_excludes_ci_true` (around line 224): the old assertion is roughly `assert count == 100`. Change the local from `count` to `result` and assert `assert sum(result.values()) == 100`.

`test_run_pypinfo_returns_zero_when_rows_empty` (around line 373): old assertion is `assert count == 0`. Change to `result = run_pypinfo(...)` then `assert sum(result.values()) == 0`.

`test_run_pypinfo_real_subprocess_passes_env_to_child` (around line 102): the test exercises real-subprocess transport, asserts the count equals what the fake pypinfo shim emits. Change to `result = run_pypinfo(...)` then assert `sum(result.values()) == <expected>`.

`test_run_pypinfo_isolates_state_so_env_var_wins_over_persisted_creds` (around line 152): same shape as above — adapt to `sum(result.values())`.

`test_run_pypinfo_filters_out_non_allowlisted_installers` (around line 247): adapt to `sum(result.values())`.

`test_run_pypinfo_allowlist_covers_packaging_tool_family` (around line 289): the test asserts that all six allowlisted installers contribute. Adapt assertion to `assert sum(result.values()) == <total>` AND keep the per-installer test by adding `assert all(result[name] > 0 for name in ("pip", "pipenv", "pipx", "uv", "poetry", "pdm"))`.

`test_run_pypinfo_allowlist_is_case_sensitive` (around line 320): adapt `count` to `sum(result.values())`.

The eighth assignment (around line 380) is `count = run_pypinfo("newpkg", ...)` for the empty-rows case — adapt as above.

(If `grep` finds additional matches not listed above, treat them the same way: rename local, assert on `sum(...)`.)

- [ ] **Step 7: Run the full test suite — verify PASS**

```bash
uv run pytest --cov
```

Expected: 73 passed (71 pre-existing + 2 new from this task), 100.00% coverage maintained, `Required test coverage of 100.0% reached.`

- [ ] **Step 8: Lint / format / typecheck**

```bash
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/pypi_winnow_downloads/
```

Expected: all clean. The mypy check is load-bearing here since the return-type annotation change is the whole point of the task.

- [ ] **Step 9: Commit**

```bash
cd /home/cmeans/.claude/worktrees/pypi-winnow-downloads-installer-mix
git add src/pypi_winnow_downloads/collector.py tests/test_collector.py
git commit -m "$(cat <<'EOF'
refactor(collector): run_pypinfo returns dict[str, int] instead of int

Preserves the per-installer breakdown that the BigQuery query already
produces (pivot by `ci AND installer` since v0.1.0). v1 summed it into a
single int; v2 needs the breakdown for per-installer badges. Six-keyed
dict, ordered via new _INSTALLER_NAMES tuple, zero-filled for installers
with no rows in the window.

No behavior change to the v1 hero badge — caller in _collect_one will
sum the dict's values to recover the same int (next task).

Existing tests that asserted on the int return adapt to assert on
sum(result.values()); two new tests cover the dict shape directly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `PackageOutcome.counts` field

`PackageOutcome` will carry the per-installer dict alongside the existing summed `count`. This unblocks Task 3 (writing more files in `_collect_one`) and Task 4 (expanding `_write_health` to include the dict).

**Files:**
- Modify: `src/pypi_winnow_downloads/collector.py:71-80` (PackageOutcome dataclass)
- Test: `tests/test_collector.py` (add 1 new test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_collector.py` near the other `PackageOutcome` tests (look for existing `PackageOutcome(` constructor calls; place this near the first one):

```python
def test_package_outcome_carries_per_installer_counts() -> None:
    outcome = PackageOutcome(
        package="foo",
        window_days=30,
        count=100,
        counts={"pip": 50, "pipenv": 1, "pipx": 2, "uv": 30, "poetry": 11, "pdm": 6, "pip-family": 53},
    )
    assert outcome.counts == {"pip": 50, "pipenv": 1, "pipx": 2, "uv": 30, "poetry": 11, "pdm": 6, "pip-family": 53}
    assert outcome.count == 100  # backwards-compat field unchanged

    # Default for failure path: no counts.
    failed = PackageOutcome(package="bar", window_days=30, count=None, error="boom")
    assert failed.counts is None
```

You'll also need to add `PackageOutcome` to the imports at the top of `test_collector.py` if it isn't already imported (check the existing import list around line 15).

- [ ] **Step 2: Run test — verify FAIL**

```bash
uv run pytest tests/test_collector.py::test_package_outcome_carries_per_installer_counts -v
```

Expected: FAIL with `TypeError: PackageOutcome.__init__() got an unexpected keyword argument 'counts'`.

- [ ] **Step 3: Add the `counts` field**

Modify `src/pypi_winnow_downloads/collector.py:71-80`. Replace the `PackageOutcome` definition with:

```python
@dataclass(frozen=True)
class PackageOutcome:
    package: str
    window_days: int
    count: int | None
    counts: dict[str, int] | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None
```

The new `counts` field is optional (defaults to `None`) so the failure-path constructor at `_collect_one`'s `except` arm doesn't need to change. The success path will populate it in Task 3.

- [ ] **Step 4: Run test — verify PASS**

```bash
uv run pytest tests/test_collector.py::test_package_outcome_carries_per_installer_counts -v
```

Expected: PASS.

- [ ] **Step 5: Run the full suite to confirm no regression**

```bash
uv run pytest --cov
```

Expected: 74 passed, 100% coverage. (Adding an optional field with a default doesn't add an uncovered branch.)

- [ ] **Step 6: Commit**

```bash
git add src/pypi_winnow_downloads/collector.py tests/test_collector.py
git commit -m "$(cat <<'EOF'
feat(collector): PackageOutcome carries per-installer counts dict

Adds optional `counts: dict[str, int] | None = None` field. Populated on
success path (next task), None on failure path (unchanged failure
constructor). The pre-existing top-level `count` (the v1 hero sum) stays
verbatim — this is purely additive so anything reading PackageOutcome
today continues to work.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `_collect_one` writes 8 badge files per successful package

The core of v2: per-package, write the v1 hero file (unchanged) plus seven per-installer files (six individual + pip-family aggregate). Drive the per-installer writes from a module-level spec tuple so the relationship between filename, label, and counts-dict key is visible at a glance.

**Files:**
- Modify: `src/pypi_winnow_downloads/collector.py:25-27, 236-268` (constants + `_collect_one`)
- Test: `tests/test_collector.py` (add 3 new tests)

- [ ] **Step 1: Add the per-installer badge spec constants**

Modify `src/pypi_winnow_downloads/collector.py` between line 27 (after `_HEALTH_FILENAME`) and line 29 (before the existing `_INSTALLER_ALLOWLIST` comment block). Insert:

```python

# Per-installer badge specs: (filename_template, label_template, counts_key).
# `counts_key` looks up the value in the per-installer dict that
# `_collect_one` builds. The "pip-family" entry is computed by `_collect_one`
# (sum of pip + pipenv + pipx) and added to the dict before iteration. Order
# matches the README dogfood layout.
_INSTALLER_BADGE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("installer-pip-{days}d-non-ci.json",         "pip ({days}d)",        "pip"),
    ("installer-pipenv-{days}d-non-ci.json",      "pipenv ({days}d)",     "pipenv"),
    ("installer-pipx-{days}d-non-ci.json",        "pipx ({days}d)",       "pipx"),
    ("installer-uv-{days}d-non-ci.json",          "uv ({days}d)",         "uv"),
    ("installer-poetry-{days}d-non-ci.json",      "poetry ({days}d)",     "poetry"),
    ("installer-pdm-{days}d-non-ci.json",         "pdm ({days}d)",        "pdm"),
    ("installer-pip-family-{days}d-non-ci.json",  "pip* ({days}d)",       "pip-family"),
)
```

- [ ] **Step 2: Write the failing test for 8 files emitted**

Add to `tests/test_collector.py` near the other `collect()` tests (around line 540, after `test_collect_writes_badge_file_per_package_with_window_in_filename`):

```python
def test_collect_writes_eight_files_per_successful_package(tmp_path: Path) -> None:
    creds = tmp_path / "key.json"
    creds.write_text("{}")
    output_dir = tmp_path / "out"

    rows = [
        {"installer_name": "pip", "ci": "False", "download_count": 50},
        {"installer_name": "pipenv", "ci": "False", "download_count": 1},
        {"installer_name": "pipx", "ci": "False", "download_count": 2},
        {"installer_name": "uv", "ci": "False", "download_count": 60},
        {"installer_name": "poetry", "ci": "False", "download_count": 11},
        {"installer_name": "pdm", "ci": "False", "download_count": 3},
    ]

    def fake_runner(argv: Sequence[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(argv), returncode=0, stdout=json.dumps({"rows": rows}), stderr=""
        )

    config = Config(
        service=ServiceConfig(
            credential_file=creds,
            output_dir=output_dir,
            stale_threshold_days=3,
        ),
        packages=(PackageConfig(name="mypkg", window_days=30),),
    )

    collect(config, runner=fake_runner)

    pkg_dir = output_dir / "mypkg"
    expected = {
        "downloads-30d-non-ci.json",
        "installer-pip-30d-non-ci.json",
        "installer-pipenv-30d-non-ci.json",
        "installer-pipx-30d-non-ci.json",
        "installer-uv-30d-non-ci.json",
        "installer-poetry-30d-non-ci.json",
        "installer-pdm-30d-non-ci.json",
        "installer-pip-family-30d-non-ci.json",
    }
    assert {p.name for p in pkg_dir.iterdir()} == expected


def test_collect_pip_family_aggregate_equals_pip_plus_pipenv_plus_pipx(tmp_path: Path) -> None:
    creds = tmp_path / "key.json"
    creds.write_text("{}")
    output_dir = tmp_path / "out"

    rows = [
        {"installer_name": "pip", "ci": "False", "download_count": 50},
        {"installer_name": "pipenv", "ci": "False", "download_count": 1},
        {"installer_name": "pipx", "ci": "False", "download_count": 2},
        {"installer_name": "uv", "ci": "False", "download_count": 60},
    ]

    def fake_runner(argv: Sequence[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(argv), returncode=0, stdout=json.dumps({"rows": rows}), stderr=""
        )

    config = Config(
        service=ServiceConfig(
            credential_file=creds,
            output_dir=output_dir,
            stale_threshold_days=3,
        ),
        packages=(PackageConfig(name="mypkg", window_days=30),),
    )

    collect(config, runner=fake_runner)

    family_path = output_dir / "mypkg" / "installer-pip-family-30d-non-ci.json"
    payload = json.loads(family_path.read_text())
    # 50 + 1 + 2 = 53; format_count emits the integer as-is for small numbers.
    assert payload["message"] == "53"
    assert payload["label"] == "pip* (30d)"


def test_collect_v1_hero_count_unchanged_against_pre_v2_fixture(tmp_path: Path) -> None:
    """Regression: the v1 hero badge value for a given pypinfo response must
    equal sum(per-installer counts), preserving the contract that pre-v2
    consumers of `downloads-<N>d-non-ci.json` rely on."""
    creds = tmp_path / "key.json"
    creds.write_text("{}")
    output_dir = tmp_path / "out"

    rows = [
        {"installer_name": "pip", "ci": "False", "download_count": 50},
        {"installer_name": "pipenv", "ci": "False", "download_count": 1},
        {"installer_name": "pipx", "ci": "False", "download_count": 2},
        {"installer_name": "uv", "ci": "False", "download_count": 60},
        {"installer_name": "poetry", "ci": "False", "download_count": 11},
        {"installer_name": "pdm", "ci": "False", "download_count": 3},
        # Excluded from hero by design — these must not contribute.
        {"installer_name": "bandersnatch", "ci": "False", "download_count": 999},
        {"installer_name": "pip", "ci": "True", "download_count": 1000},
    ]

    def fake_runner(argv: Sequence[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(argv), returncode=0, stdout=json.dumps({"rows": rows}), stderr=""
        )

    config = Config(
        service=ServiceConfig(
            credential_file=creds,
            output_dir=output_dir,
            stale_threshold_days=3,
        ),
        packages=(PackageConfig(name="mypkg", window_days=30),),
    )

    collect(config, runner=fake_runner)

    hero_path = output_dir / "mypkg" / "downloads-30d-non-ci.json"
    payload = json.loads(hero_path.read_text())
    # 50 + 1 + 2 + 60 + 11 + 3 = 127; format_count emits "127" for small numbers.
    assert payload["message"] == "127"
    assert payload["label"] == "pip*/uv/poetry/pdm (30d)"
```

(Confirm `Config`, `ServiceConfig`, `PackageConfig` are imported at the top of `test_collector.py`. They almost certainly already are — used by every other `collect()` test.)

- [ ] **Step 3: Run new tests — verify FAIL**

```bash
uv run pytest tests/test_collector.py::test_collect_writes_eight_files_per_successful_package tests/test_collector.py::test_collect_pip_family_aggregate_equals_pip_plus_pipenv_plus_pipx tests/test_collector.py::test_collect_v1_hero_count_unchanged_against_pre_v2_fixture -v
```

Expected: all 3 FAIL. The first two fail because per-installer files don't exist yet (`pkg_dir.iterdir()` returns just `downloads-30d-non-ci.json`); the third may pass if the v1 hero is still correctly computed. Either way, run the trio first to confirm the 8-file expectation isn't met.

- [ ] **Step 4: Modify `_collect_one` to emit 8 files**

Modify `src/pypi_winnow_downloads/collector.py:236-268`. Replace the existing `_collect_one` function with:

```python
def _collect_one(
    pkg: PackageConfig,
    config: Config,
    runner: Runner,
) -> PackageOutcome:
    try:
        per_installer = run_pypinfo(
            pkg.name,
            pkg.window_days,
            credential_file=config.service.credential_file,
            runner=runner,
        )
        # Compute the v1 hero total + the pip-family aggregate. Build a single
        # dict so the per-installer badge writer below can do a uniform lookup.
        hero_total = sum(per_installer.values())
        counts: dict[str, int] = {
            **per_installer,
            "pip-family": (
                per_installer["pip"] + per_installer["pipenv"] + per_installer["pipx"]
            ),
        }

        # v1 hero badge — kept verbatim for backwards compatibility with any
        # README, monitoring, or automation that reads downloads-<N>d-non-ci.json.
        hero_path = (
            config.service.output_dir
            / pkg.name
            / _BADGE_FILENAME_TEMPLATE.format(days=pkg.window_days)
        )
        badge.write_badge(
            path=hero_path,
            payload=badge.build_payload(
                count=hero_total,
                label=_BADGE_LABEL_TEMPLATE.format(days=pkg.window_days),
            ),
        )

        # Per-installer badges (six individual + pip-family aggregate).
        for fname_tpl, label_tpl, key in _INSTALLER_BADGE_SPECS:
            installer_path = (
                config.service.output_dir
                / pkg.name
                / fname_tpl.format(days=pkg.window_days)
            )
            badge.write_badge(
                path=installer_path,
                payload=badge.build_payload(
                    count=counts[key],
                    label=label_tpl.format(days=pkg.window_days),
                ),
            )
    except (CollectorError, OSError) as e:
        # Per-package isolation: a single package's BigQuery failure or disk
        # write failure must not abort the whole run, and must not skip the
        # _health.json write. Operators rely on _health.json as the single
        # diagnostic surface for the v1 staleness mechanism.
        logger.error("collector: %s", e)
        return PackageOutcome(
            package=pkg.name, window_days=pkg.window_days, count=None, error=str(e)
        )

    logger.info(
        "collector: wrote %d badges for %s (hero count=%d, path=%s)",
        1 + len(_INSTALLER_BADGE_SPECS),
        pkg.name,
        hero_total,
        hero_path.parent,
    )
    return PackageOutcome(
        package=pkg.name,
        window_days=pkg.window_days,
        count=hero_total,
        counts=counts,
    )
```

- [ ] **Step 5: Run the three new tests — verify PASS**

```bash
uv run pytest tests/test_collector.py::test_collect_writes_eight_files_per_successful_package tests/test_collector.py::test_collect_pip_family_aggregate_equals_pip_plus_pipenv_plus_pipx tests/test_collector.py::test_collect_v1_hero_count_unchanged_against_pre_v2_fixture -v
```

Expected: all 3 PASS.

- [ ] **Step 6: Run the full test suite**

```bash
uv run pytest --cov
```

Expected: 77 passed (74 from after Task 2 + 3 new), 100% coverage.

If any pre-existing `collect()` test asserted on the package directory containing exactly one file (e.g., `len(list(pkg_dir.iterdir())) == 1`), update it to assert on 8. Search:

```bash
grep -n 'iterdir\|listdir\|len(.*\.glob' tests/test_collector.py
```

Adapt any such assertion to expect 8 files.

- [ ] **Step 7: Lint / format / typecheck**

```bash
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/pypi_winnow_downloads/
```

Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add src/pypi_winnow_downloads/collector.py tests/test_collector.py
git commit -m "$(cat <<'EOF'
feat(collector): emit per-installer + pip-family badge files

Per package per window, _collect_one now writes 8 badge JSON files: the
existing v1 hero (downloads-<N>d-non-ci.json, unchanged) plus seven new:
installer-{pip,pipenv,pipx,uv,poetry,pdm,pip-family}-<N>d-non-ci.json.
Counts sourced from the per-installer dict run_pypinfo now returns;
pip-family aggregate (pip + pipenv + pipx) computed in collect.

Module-level _INSTALLER_BADGE_SPECS tuple drives the per-installer
writes, keeping the relationship between filename, label, and dict key
visible at a glance. v1 hero stays as an explicit write so its
slightly-different label format isn't buried in the spec list.

PackageOutcome.counts is now populated on success.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `_health.json` includes per-installer counts map

Additive expansion of the per-package entry in `_health.json`. Top-level `count` field unchanged (anything monitoring it keeps working); new `counts` map sits alongside.

**Files:**
- Modify: `src/pypi_winnow_downloads/collector.py:319-341` (`_write_health`)
- Test: `tests/test_collector.py` (add 2 new tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_collector.py` near the other `_health.json` tests (search for `_health.json` to find the cluster, around line 543):

```python
def test_health_file_includes_per_installer_counts_map(tmp_path: Path) -> None:
    creds = tmp_path / "key.json"
    creds.write_text("{}")
    output_dir = tmp_path / "out"

    rows = [
        {"installer_name": "pip", "ci": "False", "download_count": 50},
        {"installer_name": "pipenv", "ci": "False", "download_count": 1},
        {"installer_name": "pipx", "ci": "False", "download_count": 2},
        {"installer_name": "uv", "ci": "False", "download_count": 60},
        {"installer_name": "poetry", "ci": "False", "download_count": 11},
        {"installer_name": "pdm", "ci": "False", "download_count": 3},
    ]

    def fake_runner(argv: Sequence[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(argv), returncode=0, stdout=json.dumps({"rows": rows}), stderr=""
        )

    config = Config(
        service=ServiceConfig(
            credential_file=creds,
            output_dir=output_dir,
            stale_threshold_days=3,
        ),
        packages=(PackageConfig(name="mypkg", window_days=30),),
    )

    collect(config, runner=fake_runner)

    health = json.loads((output_dir / "_health.json").read_text())
    pkg_entry = health["packages"]["mypkg"]
    assert pkg_entry["counts"] == {
        "pip": 50,
        "pipenv": 1,
        "pipx": 2,
        "uv": 60,
        "poetry": 11,
        "pdm": 3,
        "pip-family": 53,
    }


def test_health_file_top_level_count_preserved(tmp_path: Path) -> None:
    """Backcompat: anything reading _health.json's per-package `count`
    field today (monitoring, scripts, the live CT 112 deploy) must keep
    seeing the v1 hero total — sum of all six allowlisted installers.
    The new `counts` map is purely additive."""
    creds = tmp_path / "key.json"
    creds.write_text("{}")
    output_dir = tmp_path / "out"

    rows = [
        {"installer_name": "pip", "ci": "False", "download_count": 50},
        {"installer_name": "pipenv", "ci": "False", "download_count": 1},
        {"installer_name": "pipx", "ci": "False", "download_count": 2},
        {"installer_name": "uv", "ci": "False", "download_count": 60},
        {"installer_name": "poetry", "ci": "False", "download_count": 11},
        {"installer_name": "pdm", "ci": "False", "download_count": 3},
    ]

    def fake_runner(argv: Sequence[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(argv), returncode=0, stdout=json.dumps({"rows": rows}), stderr=""
        )

    config = Config(
        service=ServiceConfig(
            credential_file=creds,
            output_dir=output_dir,
            stale_threshold_days=3,
        ),
        packages=(PackageConfig(name="mypkg", window_days=30),),
    )

    collect(config, runner=fake_runner)

    health = json.loads((output_dir / "_health.json").read_text())
    assert health["packages"]["mypkg"]["count"] == 127  # 50 + 1 + 2 + 60 + 11 + 3
    assert health["packages"]["mypkg"]["window_days"] == 30
```

- [ ] **Step 2: Run new tests — verify FAIL**

```bash
uv run pytest tests/test_collector.py::test_health_file_includes_per_installer_counts_map tests/test_collector.py::test_health_file_top_level_count_preserved -v
```

Expected: the first FAILS with `KeyError: 'counts'` (the field doesn't exist in the per-package dict yet). The second may PASS already (Task 3 populates `count` correctly), but run it now anyway as a regression check.

- [ ] **Step 3: Modify `_write_health` to include `counts`**

Modify `src/pypi_winnow_downloads/collector.py:319-341` (the `_write_health` function). Replace the body with:

```python
def _write_health(
    output_dir: Path,
    started: datetime,
    finished: datetime,
    outcomes: list[PackageOutcome],
) -> None:
    packages_section: dict[str, dict[str, Any]] = {}
    for o in outcomes:
        if o.ok:
            entry: dict[str, Any] = {"count": o.count, "window_days": o.window_days}
            if o.counts is not None:
                entry["counts"] = o.counts
            packages_section[o.package] = entry
        else:
            packages_section[o.package] = {"error": o.error, "window_days": o.window_days}

    payload = {
        "started": started.isoformat(),
        "finished": finished.isoformat(),
        "packages": packages_section,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    health_path = output_dir / _HEALTH_FILENAME
    tmp = health_path.parent / (_HEALTH_FILENAME + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, health_path)
```

The `if o.counts is not None` guard handles the failure path (where Task 2 left `counts` defaulting to `None`). Failure entries continue to look exactly as they did pre-v2.

- [ ] **Step 4: Run new tests — verify PASS**

```bash
uv run pytest tests/test_collector.py::test_health_file_includes_per_installer_counts_map tests/test_collector.py::test_health_file_top_level_count_preserved -v
```

Expected: both PASS.

- [ ] **Step 5: Run the full suite**

```bash
uv run pytest --cov
```

Expected: 79 passed, 100% coverage.

- [ ] **Step 6: Lint / typecheck**

```bash
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/pypi_winnow_downloads/
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/pypi_winnow_downloads/collector.py tests/test_collector.py
git commit -m "$(cat <<'EOF'
feat(collector): _health.json carries per-installer counts map

Per-package successful entry in _health.json gains a `counts` field
with the six allowlisted installers + pip-family aggregate. Top-level
`count` field preserved verbatim — anything reading _health.json today
(monitoring, the live deploy, future scripts) keeps working unchanged.

Failure-path entries unchanged: { error, window_days }, no counts key.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: README dogfood row + endpoint instructions section

Two prose changes: expand the dogfood badge row to include all six individual installer badges, and add a new `## Use this service for your own package` section documenting the URL pattern for shields.io endpoint badges.

**Files:**
- Modify: `README.md:8` (dogfood row, after the existing v1 hero badge line)
- Modify: `README.md` (insert new section between `## Install` and `## Status`, around line 78)
- Test: there's no automated test for README prose. The lint check below greps for the expected literal strings as a smoke test.

- [ ] **Step 1: Read the current README to confirm line numbers**

```bash
cat -n README.md | head -90
```

Confirm: line 8 is the v1 hero badge `[![pip*/uv/poetry/pdm downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Fdownloads-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)`. Line 78 is the blank line between `## Install`'s last paragraph and `## Status`. Adjust the line numbers below if your local README differs.

- [ ] **Step 2: Expand the dogfood badge row (insert 6 lines after line 8)**

Use the Edit tool. Replace the v1 hero badge line plus its trailing blank line with the v1 hero, followed by 6 new individual installer badge lines, followed by the original trailing blank line. Concretely, replace this block:

```
[![pip*/uv/poetry/pdm downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Fdownloads-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)

Self-hosted PyPI download badge service that winnows CI traffic out of download
```

With:

```
[![pip*/uv/poetry/pdm downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Fdownloads-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)
[![pip downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Finstaller-pip-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)
[![pipenv downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Finstaller-pipenv-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)
[![pipx downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Finstaller-pipx-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)
[![uv downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Finstaller-uv-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)
[![poetry downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Finstaller-poetry-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)
[![pdm downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Finstaller-pdm-30d-non-ci.json)](https://pypi.org/project/pypi-winnow-downloads/)

Self-hosted PyPI download badge service that winnows CI traffic out of download
```

- [ ] **Step 3: Insert the new "Use this service for your own package" section between Install and Status**

Use the Edit tool. The current README ends `## Install` with the deploy/README.md pointer paragraph; immediately above the next `## Status` header, insert a new section. Replace:

```
[`deploy/README.md`](https://github.com/cmeans/pypi-winnow-downloads/blob/main/deploy/README.md).

## Status
```

With:

```
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
```

- [ ] **Step 4: Verify the README parses as expected (smoke check)**

```bash
grep -c 'installer-pip-30d-non-ci.json' README.md
```

Expected: at least 2 (one in the dogfood row's `pip` badge URL, one in the new section's table). If the deployment URL pattern in the new section differs from the dogfood row's, this grep also catches it.

```bash
grep -c '## Use this service for your own package' README.md
```

Expected: exactly 1.

- [ ] **Step 5: Confirm full test suite still green (README touches no code)**

```bash
uv run pytest --cov
```

Expected: 79 passed, 100% coverage. (No code change.)

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs(readme): expand dogfood badge row + add endpoint instructions

Dogfood badge row for pypi-winnow-downloads itself now shows all six
individual installer counts alongside the existing v1 hero —
demonstrating the per-installer breakdown the v2 collector emits.

New "Use this service for your own package" section between Install
and Status documents the URL pattern for all eight badge files (v1
hero + six individual + pip-family aggregate), with copy-pasteable
markdown for embedding any of them in a third-party README. Includes
the URL-encoding gotcha (%2F / %3A) that shields.io's endpoint
argument requires.

README is pyproject.toml's long_description, so the new section also
lands on the PyPI project page.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: CHANGELOG entry under [Unreleased]

Single `### Added` bullet describing all of the above changes. Mirrors the prose-density of recent v0.1.x CHANGELOG entries.

**Files:**
- Modify: `CHANGELOG.md:8-10` (the existing `## [Unreleased]` block)

- [ ] **Step 1: Read the current `## [Unreleased]` section to confirm structure**

```bash
sed -n '7,15p' CHANGELOG.md
```

After the v0.1.3 release was cut, `## [Unreleased]` should be empty (just the header, then a blank line, then `## [0.1.3] - 2026-04-28`). Confirm before adding the new entry.

- [ ] **Step 2: Insert the `### Added` block under `## [Unreleased]`**

Use the Edit tool. Replace:

```
## [Unreleased]

## [0.1.3] - 2026-04-28
```

With:

```
## [Unreleased]

### Added

- **Per-installer badge files (v2 installer-mix feature).** The collector now emits seven additional shields.io endpoint badge JSON files per package per window, alongside the existing v1 hero (`downloads-<N>d-non-ci.json`, unchanged). New files: `installer-pip-<N>d-non-ci.json`, `installer-pipenv-<N>d-non-ci.json`, `installer-pipx-<N>d-non-ci.json`, `installer-uv-<N>d-non-ci.json`, `installer-poetry-<N>d-non-ci.json`, `installer-pdm-<N>d-non-ci.json`, and `installer-pip-family-<N>d-non-ci.json` (the pip-family aggregate = pip + pipenv + pipx). All seven apply the same `details.ci != True` filter as v1, with each file's `installer_name` allowlisting handled by the existing `_INSTALLER_ALLOWLIST`. The badge label format follows v1's parameterized `(Nd)` style — e.g., `pip (30d)`, `pip* (30d)`. Color logic (`blue` if count ≥ 10 else `lightgrey`) and the count-formatting helper (`format_count`) are unchanged. `run_pypinfo`'s return type changes from `int` to `dict[str, int]` mapping `installer_name` → count; the v1 hero count is now `sum(per_installer.values())`. `_health.json` per-package successful entries gain a `counts` field carrying the seven-keyed dict; the existing top-level `count` field is preserved verbatim for backwards compatibility with any monitoring or scripting that reads it. README expanded to dogfood all six individual installer counts in the badge row and gains a new "Use this service for your own package" section documenting the URL pattern for third-party packages. No new config fields — the collector always emits all eight files; maintainer's README picks which to display via shields.io endpoint URLs. Backwards-compat guarantees: `downloads-<N>d-non-ci.json` filename, schema, and value unchanged for any given pypinfo response; `_health.json` top-level fields unchanged. Spec: `docs/superpowers/specs/2026-04-28-installer-mix-badge-design.md`.

## [0.1.3] - 2026-04-28
```

- [ ] **Step 3: Confirm Keep-a-Changelog ordering and idempotency**

```bash
grep -A 2 '^## \[Unreleased\]' CHANGELOG.md | head -5
```

Expected: `## [Unreleased]` followed by `### Added` (Keep-a-Changelog v1.1.0 ordering — Added is the first subsection).

```bash
grep -c 'installer-pip-family' CHANGELOG.md
```

Expected: at least 1 (just landed). If 0, the edit didn't take.

- [ ] **Step 4: Run the publish.yml extractor against [Unreleased] as a smoke test**

This validates the new entry would extract correctly when the next release tag is cut. The extractor lives inline in `.github/workflows/publish.yml`, but we can run the same awk locally:

```bash
awk -v ver="Unreleased" '
  found && /^## \[/ { exit }
  found && /^\[[^]]+\]:[[:space:]]/ { exit }
  $0 ~ "^## \\[" ver "\\]" { found=1; next }
  found { lines[++n] = $0 }
  END {
    start = 1
    while (start <= n && lines[start] == "") start++
    end = n
    while (end >= start && lines[end] == "") end--
    for (i = start; i <= end; i++) print lines[i]
  }
' CHANGELOG.md | head
```

Expected: prints `### Added` followed by the bullet's first lines. The full extraction is what the next release tag would put in the GitHub release page body.

- [ ] **Step 5: Final full-suite check**

```bash
uv run pytest --cov && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/pypi_winnow_downloads/
```

Expected: 79 passed, 100% coverage, all linters clean.

- [ ] **Step 6: Commit**

```bash
git add CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs(changelog): add installer-mix v2 entry under [Unreleased]

Single ### Added bullet covering: seven new per-installer badge files
(six individual + pip-family aggregate), v1 hero unchanged, _health.json
per-package counts map (additive), README dogfood + endpoint instructions,
zero-knob configuration. References the spec doc for the design rationale
and the backwards-compat guarantees.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Push branch + open PR

After all six implementation tasks land cleanly with green CI signals locally, push and open the PR.

**Files:** none modified by this task.

- [ ] **Step 1: Confirm branch state**

```bash
cd /home/cmeans/.claude/worktrees/pypi-winnow-downloads-installer-mix
git log --oneline origin/main..HEAD
```

Expected: 6-7 commits (one per task plus the spec commit `767b56e` if you didn't already push it earlier). If the spec commit isn't in the list, that's fine — it'll go up with the rest.

- [ ] **Step 2: Push branch**

```bash
FRESH_TOKEN=$(/home/cmeans/github.com/cmeans/claude-dev/github-app/get-token.sh)
GH_TOKEN="$FRESH_TOKEN" git push -u origin feat/installer-mix
```

Expected: branch pushed to origin, no auth errors.

- [ ] **Step 3: Open PR**

```bash
FRESH_TOKEN=$(/home/cmeans/github.com/cmeans/claude-dev/github-app/get-token.sh)
GH_TOKEN="$FRESH_TOKEN" gh pr create --repo cmeans/pypi-winnow-downloads --base main --head feat/installer-mix --title "feat(collector): add per-installer badge files (installer-mix v2)" --body "$(cat <<'EOF'
## Summary

First v2 badge candidate from the project's "Future badge candidates" backlog: per-installer breakdown of non-CI downloads, surfaced as seven additional shields.io endpoint badge JSON files per package per window (six individual installers + a `pip-family` aggregate). v1 hero kept side-by-side, additive throughout.

## What's in the diff

- `run_pypinfo` returns `dict[str, int]` instead of `int` (allowlist filter and CI filter unchanged; six-keyed dict, zero-filled).
- `_collect_one` writes 8 badge files per successful package (1 v1 hero + 7 v2).
- `PackageOutcome.counts: dict[str, int] | None` carries the per-installer breakdown.
- `_health.json` per-package entries gain a `counts` field (additive; top-level `count` preserved).
- `README.md` dogfood badge row expanded with the six individual installer badges; new `## Use this service for your own package` section documents the URL pattern for third-party packages.
- `CHANGELOG.md` `[Unreleased]` gets one `### Added` bullet.

## Spec / plan

- Spec: [`docs/superpowers/specs/2026-04-28-installer-mix-badge-design.md`](docs/superpowers/specs/2026-04-28-installer-mix-badge-design.md)
- Plan: [`docs/superpowers/plans/2026-04-28-installer-mix-badge.md`](docs/superpowers/plans/2026-04-28-installer-mix-badge.md)

Decisions made during brainstorming (Form A absolute counts / B3 bucketing / C1 non-CI filter only / no per-installer brand colors / no per-package configurability) all trace to the spec.

## Backwards compatibility

- `downloads-<N>d-non-ci.json` filename, schema, and value unchanged for any given pypinfo response. Regression test locks this in (`test_collect_v1_hero_count_unchanged_against_pre_v2_fixture`).
- `_health.json` top-level fields unchanged. Per-package `count` field unchanged. New `counts` map is purely additive.

## Version bump

This PR ships the feature; the v0.2.0 release PR (separate, follows the v0.1.3 release flow) ships the version bump. Minor bump justified because `run_pypinfo`'s return type changes; the file isn't `_underscore`-prefixed and its shape is exercised in tests.

## Test plan

- [ ] CI passes: lint, typecheck, test (3.11/3.12/3.13), deploy-smoke, all green
- [ ] Coverage gate (`fail_under = 100`) maintained — locally: 6 new tests + 7 adapted, total ~79 tests
- [ ] On the next `v*` tag, `publish.yml` extracts the `## [Unreleased] ### Added` block via the new awk extractor (validated locally)
- [ ] After deploying to CT 112, smoke-check that all 8 badge files appear under `https://pypi-badges.intfar.com/<package>/` for each configured package; spot-check one badge endpoint via `curl | jq` to confirm shape

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

- [ ] **Step 4: Verify the PR landed and CI started**

```bash
FRESH_TOKEN=$(/home/cmeans/github.com/cmeans/claude-dev/github-app/get-token.sh)
GH_TOKEN="$FRESH_TOKEN" gh pr view --repo cmeans/pypi-winnow-downloads --json number,url,statusCheckRollup --jq '{number, url, checks: [.statusCheckRollup[] | {name, status}]}'
```

Expected: PR number printed, URL listed, several checks in `IN_PROGRESS` or `QUEUED` state.

---

## Self-Review

Spec coverage check (against `docs/superpowers/specs/2026-04-28-installer-mix-badge-design.md`):

- ✅ Per-installer badge breakdown — Task 3 (constants + 8-file write loop)
- ✅ pip-family aggregate — Task 3 (computed in `_collect_one`)
- ✅ v1 hero unchanged — Task 3 (kept as explicit write; regression test locks the value)
- ✅ Health-file schema additive expansion — Task 4
- ✅ README dogfood + instructions — Task 5
- ✅ CHANGELOG `### Added` entry — Task 6
- ✅ `run_pypinfo` signature change — Task 1
- ✅ All 6 tests from the spec's test list — Tasks 1, 3, 4 cover them: `test_run_pypinfo_returns_per_installer_dict`, `test_collect_writes_eight_files_per_successful_package`, `test_collect_pip_family_aggregate_equals_pip_plus_pipenv_plus_pipx`, `test_collect_v1_hero_count_unchanged_against_pre_v2_fixture`, `test_health_file_includes_per_installer_counts_map`, `test_health_file_top_level_count_preserved`. Plus `test_run_pypinfo_zeroes_installers_with_no_rows` (Task 1) and `test_package_outcome_carries_per_installer_counts` (Task 2) as supporting coverage.

Placeholder scan: no TBDs, no TODOs, no "implement later" or "add appropriate error handling" — every code step has the actual code, every command has the actual command and expected output.

Type consistency check:
- `_INSTALLER_NAMES: tuple[str, ...]` (Task 1) — referenced in `run_pypinfo`'s counts initializer (Task 1) ✓
- `_INSTALLER_ALLOWLIST: frozenset[str]` (Task 1) — same membership check as before ✓
- `_INSTALLER_BADGE_SPECS: tuple[tuple[str, str, str], ...]` (Task 3) — iteration in `_collect_one`'s loop unpacks as `fname_tpl, label_tpl, key` ✓
- `PackageOutcome.counts: dict[str, int] | None = None` (Task 2) — populated in Task 3, read in Task 4 ✓
- Filename templates use `{days}` placeholder — formatted via `.format(days=pkg.window_days)` consistently ✓
- `dict[str, int]` return type for `run_pypinfo` — caller in `_collect_one` does `sum(per_installer.values())` and dict-merge, both type-safe ✓

No issues found. Plan is ready.

---

## Notes for the executor

- All changes happen in the `feat/installer-mix` worktree at `/home/cmeans/.claude/worktrees/pypi-winnow-downloads-installer-mix`. Don't commit to `main` directly.
- The bot installation token (`$GH_TOKEN`) expires after 1 hour. If a `git push` returns "Invalid username or token", re-mint via `/home/cmeans/github.com/cmeans/claude-dev/github-app/get-token.sh` and retry as `GH_TOKEN="$FRESH" git push`.
- Coverage gate is strict (`fail_under = 100` in `pyproject.toml`'s `[tool.coverage.report]` section). If a step adds an uncovered branch, the suite goes red; either add the missing test or rework the implementation to remove the unreachable path. Do NOT add `# pragma: no cover` (project rule).
- Don't bump `pyproject.toml`'s `version` field in this PR. Version bump goes in a separate release PR (`release: v0.2.0`) after this lands, mirroring the v0.1.3 flow.
