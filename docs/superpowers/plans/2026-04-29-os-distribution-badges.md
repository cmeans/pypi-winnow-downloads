# OS Distribution Badges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-OS download breakdown badges (linux / macos / windows) parallel to the per-installer breakdown shipped in v0.2.0, by extending the pypinfo group-by to a multi-dimensional `(installer, system)` query.

**Architecture:** Extend `run_pypinfo()` argv from `["ci", "installer"]` to `["ci", "installer", "system"]`. Restructure its return type from `dict[str, int]` to a TypedDict carrying `by_installer` and `by_system` aggregates. Add `_OS_BADGE_SPECS` and three new badge filenames following v2's pattern. Extend `PackageOutcome` and `_write_health()` to carry the per-system counts. README dogfood block grows a parallel "By OS" paragraph.

**Tech Stack:** Python 3.11+, `pypinfo`, BigQuery (group-by), pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-04-29-os-distribution-badge-design.md`

---

## File structure

| Path | Action | Responsibility |
| --- | --- | --- |
| `src/pypi_winnow_downloads/collector.py` | Modify | Add system constants + badge specs; change `run_pypinfo()` argv and return shape; add per-system aggregation; extend badge emission loop; update `PackageOutcome`; extend `_write_health()`. |
| `tests/test_collector.py` | Modify | New tests for: argv addition, return-shape change, per-system aggregation, system allowlist filter, edge case (allowlisted installer + non-allowlisted system), v0.2.0 hero stability invariant, OS badge file emission, `_health.json` `counts_by_system` field, existing fields preserved. |
| `README.md` | Modify | Add "By OS" paragraph to each dogfood block; add "By OS breakdown" paragraph; add 3 rows to "Use this service for your own package" table. |
| `CHANGELOG.md` | Modify | One bullet under `## [Unreleased]` → `### Added`. |
| `docs/superpowers/specs/2026-04-29-os-distribution-badge-design.md` | Already committed (Task 1 stages it from working tree) | Design spec. |
| `docs/superpowers/plans/2026-04-29-os-distribution-badges.md` | Already committed (Task 1 stages it) | This plan. |

---

## Task 1: Branch + add constants

**Files:**
- Modify: `src/pypi_winnow_downloads/collector.py` — add system constants + OS badge specs.

- [ ] **Step 1: Create the feature branch**

```bash
git checkout main
git status -sb
git checkout -b feat/os-distribution-badges
```

Expected: clean working tree on main matches origin/main, then on `feat/os-distribution-badges`. The untracked spec + plan files follow the branch.

- [ ] **Step 2: Add the new constants block**

Open `src/pypi_winnow_downloads/collector.py`. Find the `_INSTALLER_BADGE_SPECS` block (~line 34) and the `_INSTALLER_NAMES` / `_INSTALLER_ALLOWLIST` block (~line 56–61). Add a parallel `_SYSTEM_*` and `_OS_BADGE_SPECS` block immediately after `_INSTALLER_ALLOWLIST`:

```python
# System (OS) allowlist for the per-OS breakdown. The same `details.ci != True`
# filter applies as the hero. The keys are pypinfo's raw `system_name` values
# (matches BigQuery's `details.system.name` column emission); the badge
# filename slug and label use the user-friendly `macos` for `Darwin`. Long-tail
# values (BSD variants, null/empty system_name) are excluded — they neither
# contribute to per-OS aggregates nor surface as a badge.
_SYSTEM_NAMES: tuple[str, ...] = ("Linux", "Darwin", "Windows")
_SYSTEM_ALLOWLIST: frozenset[str] = frozenset(_SYSTEM_NAMES)

# Per-OS badge specs: (filename_template, label_template, counts_key).
# Order matches the README dogfood layout. `counts_key` is the raw pypinfo
# emission (matches `_SYSTEM_ALLOWLIST`); the slug/label use the user-friendly
# form. Hero count is unaffected — see spec for the v0.2.0 hero-stability
# invariant.
_OS_BADGE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("os-linux-{days}d-non-ci.json", "linux ({days}d)", "Linux"),
    ("os-macos-{days}d-non-ci.json", "macos ({days}d)", "Darwin"),
    ("os-windows-{days}d-non-ci.json", "windows ({days}d)", "Windows"),
)
```

- [ ] **Step 3: Verify the file still parses + lints clean**

```bash
uv run python -c "from pypi_winnow_downloads import collector; print(collector._SYSTEM_NAMES, collector._OS_BADGE_SPECS)"
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/pypi_winnow_downloads/
uv run pytest -x
```

Expected: imports succeed, ruff/format/mypy clean, all 79 existing tests still pass (no behavior change yet).

- [ ] **Step 4: Stage spec + plan files (untracked from prior brainstorming)**

```bash
git status -sb
git add src/pypi_winnow_downloads/collector.py docs/superpowers/specs/2026-04-29-os-distribution-badge-design.md docs/superpowers/plans/2026-04-29-os-distribution-badges.md
```

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(collector): add OS allowlist + badge specs (no behavior change)

Adds _SYSTEM_NAMES, _SYSTEM_ALLOWLIST, and _OS_BADGE_SPECS constants
parallel to the per-installer constants. No behavior change yet — the
constants are forward-declared for the v3 OS distribution feature
(filenames, labels, allowlist keys). Subsequent commits wire up the
multi-dim pypinfo query, per-system aggregation, badge emission, and
_health.json shape.

Spec: docs/superpowers/specs/2026-04-29-os-distribution-badge-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: TDD — `run_pypinfo()` multi-dim grouping

**Files:**
- Modify: `tests/test_collector.py` — add new test cases.
- Modify: `src/pypi_winnow_downloads/collector.py` — change argv, return shape, aggregation.

- [ ] **Step 1: Write the failing test for argv extension**

Open `tests/test_collector.py`. Find `test_run_pypinfo_invokes_pypinfo_with_expected_argv` (~line 29). Add a new test immediately after it:

```python
def test_run_pypinfo_argv_groups_by_ci_installer_system(tmp_path: Path) -> None:
    """v3 OS distribution: pypinfo group-by extended from `ci installer` to
    `ci installer system` so a single BigQuery call returns both dimensions."""
    captured: list[list[str]] = []

    def fake_runner(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        captured.append(list(argv))
        return _ok_result(argv)

    creds = tmp_path / "creds.json"
    creds.write_text("{}")
    run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)

    assert captured, "fake_runner was never called"
    argv = captured[0]
    # The three positional dimension args must appear in this order at the end of argv.
    assert argv[-3:] == ["ci", "installer", "system"], argv
```

- [ ] **Step 2: Write the failing tests for return shape + per-system aggregation**

Append after the new test:

```python
def _ok_rows(rows: list[dict]) -> str:
    return json.dumps({"rows": rows})


def test_run_pypinfo_returns_by_installer_and_by_system(tmp_path: Path) -> None:
    """Return shape is a structured dict with two aggregates."""
    stdout = _ok_rows([
        {"ci": "False", "download_count": 100, "installer_name": "pip", "system_name": "Linux"},
        {"ci": "False", "download_count": 30, "installer_name": "pip", "system_name": "Darwin"},
        {"ci": "False", "download_count": 20, "installer_name": "uv", "system_name": "Linux"},
        {"ci": "False", "download_count": 5, "installer_name": "uv", "system_name": "Windows"},
    ])

    def fake_runner(argv, env):
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    creds = tmp_path / "creds.json"
    creds.write_text("{}")
    result = run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)

    assert result == {
        "by_installer": {"pip": 130, "pipenv": 0, "pipx": 0, "uv": 25, "poetry": 0, "pdm": 0},
        "by_system": {"Linux": 120, "Darwin": 30, "Windows": 5},
    }


def test_run_pypinfo_filters_out_non_allowlisted_systems(tmp_path: Path) -> None:
    """Long-tail OSes (BSD, null, etc.) drop out of by_system but still
    contribute to by_installer when the installer is allowlisted — the
    v0.2.0 hero-stability invariant."""
    stdout = _ok_rows([
        {"ci": "False", "download_count": 100, "installer_name": "pip", "system_name": "Linux"},
        {"ci": "False", "download_count": 7, "installer_name": "pip", "system_name": "FreeBSD"},
        {"ci": "False", "download_count": 11, "installer_name": "pip", "system_name": ""},
        {"ci": "False", "download_count": 13, "installer_name": "pip", "system_name": "OpenBSD"},
    ])

    def fake_runner(argv, env):
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    creds = tmp_path / "creds.json"
    creds.write_text("{}")
    result = run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)

    # Hero stability: by_installer["pip"] = 100 + 7 + 11 + 13 = 131 (all 4 rows count).
    assert result["by_installer"]["pip"] == 131
    # by_system: only the Linux row counts; non-allowlisted/empty system_name rows drop out.
    assert result["by_system"] == {"Linux": 100, "Darwin": 0, "Windows": 0}


def test_run_pypinfo_excludes_ci_true_from_both_dimensions(tmp_path: Path) -> None:
    """CI traffic is filtered before either dimension's aggregation."""
    stdout = _ok_rows([
        {"ci": "True", "download_count": 9999, "installer_name": "pip", "system_name": "Linux"},
        {"ci": "None", "download_count": 50, "installer_name": "pip", "system_name": "Linux"},
        {"ci": "False", "download_count": 10, "installer_name": "pip", "system_name": "Linux"},
    ])

    def fake_runner(argv, env):
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    creds = tmp_path / "creds.json"
    creds.write_text("{}")
    result = run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)

    # CI=True row dropped; CI=None and CI=False rows count (matches v1 behavior).
    assert result["by_installer"]["pip"] == 60
    assert result["by_system"]["Linux"] == 60


def test_run_pypinfo_handles_missing_system_name_field(tmp_path: Path) -> None:
    """A row missing the system_name key entirely (older pypinfo schema or
    user-agent parsing failure) must not crash; it just doesn't contribute
    to by_system."""
    stdout = _ok_rows([
        {"ci": "False", "download_count": 42, "installer_name": "pip", "system_name": "Linux"},
        {"ci": "False", "download_count": 8, "installer_name": "pip"},  # no system_name
    ])

    def fake_runner(argv, env):
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    creds = tmp_path / "creds.json"
    creds.write_text("{}")
    result = run_pypinfo("mypkg", 30, credential_file=creds, runner=fake_runner)

    assert result["by_installer"]["pip"] == 50
    assert result["by_system"] == {"Linux": 42, "Darwin": 0, "Windows": 0}
```

- [ ] **Step 3: Run the new tests — must fail**

```bash
uv run pytest tests/test_collector.py::test_run_pypinfo_argv_groups_by_ci_installer_system tests/test_collector.py::test_run_pypinfo_returns_by_installer_and_by_system tests/test_collector.py::test_run_pypinfo_filters_out_non_allowlisted_systems tests/test_collector.py::test_run_pypinfo_excludes_ci_true_from_both_dimensions tests/test_collector.py::test_run_pypinfo_handles_missing_system_name_field -v
```

Expected: all 5 fail (argv assertion fails because "system" isn't in argv yet; return-shape assertions fail because `result` is still `dict[str, int]`).

- [ ] **Step 4: Update `run_pypinfo()` argv**

Open `src/pypi_winnow_downloads/collector.py`. Find the argv block in `run_pypinfo()` (~line 141–150). Change:

```python
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
```

to:

```python
    argv = [
        _resolve_pypinfo_path(),
        "--json",
        "--days",
        str(window_days),
        "--all",
        package,
        "ci",
        "installer",
        "system",
    ]
```

- [ ] **Step 5: Update `run_pypinfo()` return type and aggregation**

Add a `RunPypinfoResult` TypedDict near the top of the module (next to the `Runner` and `Clock` aliases, ~line 21):

```python
from typing import TypedDict


class RunPypinfoResult(TypedDict):
    by_installer: dict[str, int]
    by_system: dict[str, int]
```

Change `run_pypinfo()`'s return annotation from `dict[str, int]` to `RunPypinfoResult`.

Replace the aggregation block (the `counts: dict[str, int] = {name: 0 for name in _INSTALLER_NAMES}` block + the row loop) with:

```python
    # Initialize both dicts to zero for every allowlisted key so the returned
    # shape is stable regardless of which (installer, system) pairs had rows
    # in this window. Order follows _INSTALLER_NAMES / _SYSTEM_NAMES so callers
    # can rely on iteration order for badge filenames and tests can assert on
    # equality with specific dict literals.
    by_installer: dict[str, int] = {name: 0 for name in _INSTALLER_NAMES}
    by_system: dict[str, int] = {name: 0 for name in _SYSTEM_NAMES}
    for row in rows:
        if not isinstance(row, dict):
            raise CollectorError(
                f"pypinfo row for {package!r} has unexpected shape (not a dict): {row!r}"
            )
        if row.get("ci") == "True":
            continue
        if "installer_name" not in row:
            raise CollectorError(
                f"pypinfo row for {package!r} missing 'installer_name' field: {row!r}"
            )
        installer = row["installer_name"]
        count = row.get("download_count", 0)
        if not isinstance(count, int):
            raise CollectorError(
                f"pypinfo row for {package!r} has non-integer download_count: {count!r}"
            )

        # Per-installer aggregation: hero-stability invariant — count
        # the row regardless of system_name, as long as the installer is
        # allowlisted. v0.2.0's hero-count contract depends on this.
        if installer in _INSTALLER_ALLOWLIST:
            by_installer[installer] += count

        # Per-system aggregation: independent allowlist check. Rows with
        # missing/empty/non-allowlisted system_name drop out of by_system
        # but may still contribute to by_installer above.
        system = row.get("system_name", "")
        if system in _SYSTEM_ALLOWLIST:
            by_system[system] += count

    return {"by_installer": by_installer, "by_system": by_system}
```

- [ ] **Step 6: Run tests — they should pass; existing tests should still pass**

```bash
uv run pytest tests/test_collector.py -v
```

Expected: 5 new tests PASS, all prior tests STILL PASS (~79 existing → 84 total). If any existing test fails, it's because the existing test asserted on the old `dict[str, int]` return shape. Update those existing tests to use `result["by_installer"]` instead of `result` directly. Specifically, audit the existing tests:

```bash
grep -n 'run_pypinfo("mypkg"' tests/test_collector.py | head
```

For each such test, if the assertion looks like `assert result == {"pip": ...}`, change it to `assert result["by_installer"] == {"pip": ...}` (and add `"by_system": ...` if the test had system_name fields in its rows; otherwise leave by_system implicit).

- [ ] **Step 7: Commit**

```bash
git add src/pypi_winnow_downloads/collector.py tests/test_collector.py
git commit -m "$(cat <<'EOF'
feat(collector): pypinfo group-by ci installer system + dual-dim aggregation

Changes run_pypinfo() to query BigQuery on a 3-dimensional GROUP BY
(`ci installer system`) so a single call yields both per-installer and
per-system breakdowns. Return type changes from dict[str, int] to a
TypedDict carrying both aggregates.

The v0.2.0 hero-stability invariant is preserved: hero count
(sum(by_installer.values())) is unchanged because the per-installer
aggregation does not consider system_name. The per-system aggregation
applies an independent allowlist filter (Linux/Darwin/Windows); rows
with missing or non-allowlisted system_name drop out of by_system but
still count toward by_installer when the installer is allowlisted.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: TDD — per-OS badge file emission

**Files:**
- Modify: `tests/test_collector.py` — add badge-emission tests.
- Modify: `src/pypi_winnow_downloads/collector.py` — extend badge emission loop, update `PackageOutcome`.

- [ ] **Step 1: Read the existing badge-emission test pattern for context**

```bash
grep -n 'def test_collect_one_writes\|installer-pip-' tests/test_collector.py | head
```

Identify how the existing test asserts on the per-installer file emission. The new test should mirror that pattern.

- [ ] **Step 2: Write failing tests for the 3 new OS badge files**

Append to `tests/test_collector.py` after the existing per-installer-emission tests:

```python
def test_collect_one_writes_three_per_os_badge_files(tmp_path: Path) -> None:
    """v3 OS distribution: collector emits os-linux-30d-non-ci.json,
    os-macos-30d-non-ci.json, os-windows-30d-non-ci.json with the
    correct shields.io shape."""
    output_dir = tmp_path / "out"
    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    stdout = _ok_rows([
        {"ci": "False", "download_count": 100, "installer_name": "pip", "system_name": "Linux"},
        {"ci": "False", "download_count": 30, "installer_name": "pip", "system_name": "Darwin"},
        {"ci": "False", "download_count": 5, "installer_name": "uv", "system_name": "Windows"},
    ])

    def fake_runner(argv, env):
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    config = _make_config(packages=[("mypkg", 30)], output_dir=output_dir, credential_file=creds)
    _collect_one(config.packages[0], config, runner=fake_runner)

    pkg_dir = output_dir / "mypkg"
    linux = json.loads((pkg_dir / "os-linux-30d-non-ci.json").read_text())
    macos = json.loads((pkg_dir / "os-macos-30d-non-ci.json").read_text())
    windows = json.loads((pkg_dir / "os-windows-30d-non-ci.json").read_text())

    assert linux["label"] == "linux (30d)"
    assert linux["message"] == "100"
    assert linux["color"] == "blue"

    assert macos["label"] == "macos (30d)"
    assert macos["message"] == "30"
    assert macos["color"] == "blue"

    assert windows["label"] == "windows (30d)"
    assert windows["message"] == "5"
    # 5 < 10 → lightgrey per the existing color logic.
    assert windows["color"] == "lightgrey"


def test_collect_one_v0_2_0_files_unchanged_alongside_os_files(tmp_path: Path) -> None:
    """The v3 OS feature must not change v0.2.0's filename, schema, or value
    for any given pypinfo response. Asserts existence + shape of all
    pre-v3 files plus the 3 new OS files = 11 total per package per window."""
    output_dir = tmp_path / "out"
    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    stdout = _ok_rows([
        {"ci": "False", "download_count": 100, "installer_name": "pip", "system_name": "Linux"},
    ])

    def fake_runner(argv, env):
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    config = _make_config(packages=[("mypkg", 30)], output_dir=output_dir, credential_file=creds)
    _collect_one(config.packages[0], config, runner=fake_runner)

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
        "os-linux-30d-non-ci.json",
        "os-macos-30d-non-ci.json",
        "os-windows-30d-non-ci.json",
    }
    actual = {p.name for p in pkg_dir.iterdir()}
    assert expected == actual, f"missing: {expected - actual}, extra: {actual - expected}"

    # Hero schema unchanged.
    hero = json.loads((pkg_dir / "downloads-30d-non-ci.json").read_text())
    assert hero["message"] == "100"
    assert hero["label"] == "pip*/uv/poetry/pdm (30d)"
```

- [ ] **Step 3: Run new tests — must fail**

```bash
uv run pytest tests/test_collector.py::test_collect_one_writes_three_per_os_badge_files tests/test_collector.py::test_collect_one_v0_2_0_files_unchanged_alongside_os_files -v
```

Expected: both fail because `os-linux-30d-non-ci.json` (etc.) don't exist; the badge emission loop hasn't been extended yet.

- [ ] **Step 4: Update `PackageOutcome` dataclass**

Find `PackageOutcome` in `src/pypi_winnow_downloads/collector.py`. Add a new field `counts_by_system: dict[str, int] | None = None` next to the existing `counts` field.

- [ ] **Step 5: Update `_collect_one()` to consume the new return shape and emit OS badges**

Find the body of `_collect_one()` that calls `run_pypinfo()` and assigns `per_installer`. Replace:

```python
        per_installer = run_pypinfo(...)
        hero_total = sum(per_installer.values())
        counts: dict[str, int] = {
            **per_installer,
            "pip-family": (per_installer["pip"] + per_installer["pipenv"] + per_installer["pipx"]),
        }
```

with:

```python
        result = run_pypinfo(...)
        per_installer = result["by_installer"]
        per_system = result["by_system"]
        hero_total = sum(per_installer.values())
        counts: dict[str, int] = {
            **per_installer,
            "pip-family": (per_installer["pip"] + per_installer["pipenv"] + per_installer["pipx"]),
        }
```

After the existing per-installer badge emission loop (the `for fname_tpl, label_tpl, key in _INSTALLER_BADGE_SPECS:` block), add a parallel OS loop:

```python
        # Per-OS badges (linux + macos + windows). The counts_key matches
        # pypinfo's raw system_name emission; the slug/label use macos for
        # Darwin (user-friendly form). Hero count is unaffected.
        for fname_tpl, label_tpl, key in _OS_BADGE_SPECS:
            os_path = (
                config.service.output_dir / pkg.name / fname_tpl.format(days=pkg.window_days)
            )
            badge.write_badge(
                path=os_path,
                payload=badge.build_payload(
                    count=per_system[key],
                    label=label_tpl.format(days=pkg.window_days),
                ),
            )
```

Update the `logger.info` call's badge count:

```python
    logger.info(
        "collector: wrote %d badges for %s (hero count=%d, path=%s)",
        1 + len(_INSTALLER_BADGE_SPECS) + len(_OS_BADGE_SPECS),
        pkg.name,
        hero_total,
        hero_path.parent,
    )
```

Update the `PackageOutcome` constructor at the bottom of the success path to include `counts_by_system=per_system`:

```python
    return PackageOutcome(
        package=pkg.name,
        window_days=pkg.window_days,
        count=hero_total,
        counts=counts,
        counts_by_system=per_system,
    )
```

- [ ] **Step 6: Run tests — should pass**

```bash
uv run pytest tests/test_collector.py -v
```

Expected: all tests pass (the 2 new tests + the existing tests). If a pre-existing test asserts on the old `per_installer` dict directly (e.g., `result == {"pip": ...}`), it'll need the same `result["by_installer"]` update applied in Task 2 Step 6 (most should already be done by then; this is a safety net).

- [ ] **Step 7: Commit**

```bash
git add src/pypi_winnow_downloads/collector.py tests/test_collector.py
git commit -m "$(cat <<'EOF'
feat(collector): emit per-OS badges (linux/macos/windows)

Three new shields.io endpoint JSON files per package per window:
os-linux-Nd-non-ci.json, os-macos-Nd-non-ci.json,
os-windows-Nd-non-ci.json. Color logic and label format mirror the
per-installer badges (blue if count >= 10 else lightgrey;
parameterized by window_days).

PackageOutcome gains a counts_by_system field; v0.2.0's existing
fields are preserved verbatim. Total badge files per package per
window increases from 8 to 11.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: TDD — `_health.json` shape

**Files:**
- Modify: `tests/test_collector.py` — add `_health.json` shape tests.
- Modify: `src/pypi_winnow_downloads/collector.py` — extend `_write_health()`.

- [ ] **Step 1: Write failing tests for `counts_by_system` in `_health.json`**

Append:

```python
def test_health_json_includes_counts_by_system(tmp_path: Path) -> None:
    """v3: per-package successful entries gain counts_by_system alongside
    the existing counts field."""
    output_dir = tmp_path / "out"
    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    stdout = _ok_rows([
        {"ci": "False", "download_count": 100, "installer_name": "pip", "system_name": "Linux"},
        {"ci": "False", "download_count": 30, "installer_name": "pip", "system_name": "Darwin"},
    ])

    def fake_runner(argv, env):
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    config = _make_config(packages=[("mypkg", 30)], output_dir=output_dir, credential_file=creds)
    main(config_override=config, runner=fake_runner)  # or whatever the existing pattern uses

    health = json.loads((output_dir / "_health.json").read_text())
    pkg_entry = health["packages"]["mypkg"]
    assert pkg_entry["counts_by_system"] == {"Linux": 100, "Darwin": 30, "Windows": 0}


def test_health_json_preserves_v0_2_0_fields(tmp_path: Path) -> None:
    """v3 must not change existing _health.json fields for any given
    pypinfo response. Asserts count, counts, window_days are all present
    and have the expected v0.2.0 shape."""
    output_dir = tmp_path / "out"
    creds = tmp_path / "creds.json"
    creds.write_text("{}")

    stdout = _ok_rows([
        {"ci": "False", "download_count": 100, "installer_name": "pip", "system_name": "Linux"},
    ])

    def fake_runner(argv, env):
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    config = _make_config(packages=[("mypkg", 30)], output_dir=output_dir, credential_file=creds)
    main(config_override=config, runner=fake_runner)

    health = json.loads((output_dir / "_health.json").read_text())
    pkg_entry = health["packages"]["mypkg"]
    assert pkg_entry["count"] == 100
    assert pkg_entry["window_days"] == 30
    # Existing counts dict unchanged in v3.
    assert pkg_entry["counts"]["pip"] == 100
    assert "pip-family" in pkg_entry["counts"]
```

**Note:** the exact entry-point invocation in these tests depends on the existing pattern in `test_collector.py`. If the existing tests use `_collect_one()` directly + `_write_health()` directly rather than `main()`, mirror that. Inspect the existing `_health.json` test (search `grep -n 'health.json\|_write_health' tests/test_collector.py | head`) and use the same harness.

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_collector.py::test_health_json_includes_counts_by_system tests/test_collector.py::test_health_json_preserves_v0_2_0_fields -v
```

Expected: both fail because `_write_health()` doesn't include `counts_by_system` yet.

- [ ] **Step 3: Update `_write_health()`**

Find `_write_health()` in `src/pypi_winnow_downloads/collector.py`. In the per-package success branch, change:

```python
        if o.ok:
            entry: dict[str, Any] = {"count": o.count, "window_days": o.window_days}
            if o.counts is not None:
                entry["counts"] = o.counts
            packages_section[o.package] = entry
```

to:

```python
        if o.ok:
            entry: dict[str, Any] = {"count": o.count, "window_days": o.window_days}
            if o.counts is not None:
                entry["counts"] = o.counts
            if o.counts_by_system is not None:
                entry["counts_by_system"] = o.counts_by_system
            packages_section[o.package] = entry
```

- [ ] **Step 4: Run tests — should pass**

```bash
uv run pytest tests/test_collector.py -v
```

Expected: all 80+ tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/pypi_winnow_downloads/collector.py tests/test_collector.py
git commit -m "$(cat <<'EOF'
feat(collector): _health.json gains counts_by_system per package

Per-package successful entries in _health.json now include
counts_by_system alongside the existing counts (per-installer) field.
v0.2.0 fields (count, counts, window_days) preserved verbatim — no
change to existing monitoring or scripting that reads them.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: README updates

**Files:**
- Modify: `README.md` — dogfood block per package, breakdown paragraph, table.

- [ ] **Step 1: Identify the dogfood block structure**

```bash
grep -n '## By installer\|^**By installer\|## What these badges\|## Use this service' README.md | head
```

Note the line numbers of:
- The "By installer" paragraph (one per dogfood package)
- The "Per-installer breakdown" paragraph in "What these badges actually count"
- The "Use this service for your own package" table

- [ ] **Step 2: Add "By OS" paragraph to each dogfood package's block**

For each dogfood package (currently `pypi-winnow-downloads`, `mcp-clipboard`, `mcp-synology`, etc. — verify with `grep -n '^\*\*By installer' README.md`), insert a new paragraph immediately after the "By installer" paragraph:

```markdown
**By OS (30d, non-CI):** [![linux](https://img.shields.io/endpoint?url=https://pypi-badges.intfar.com/<package>/os-linux-30d-non-ci.json)](https://pypi-badges.intfar.com/<package>/os-linux-30d-non-ci.json) [![macos](https://img.shields.io/endpoint?url=https://pypi-badges.intfar.com/<package>/os-macos-30d-non-ci.json)](https://pypi-badges.intfar.com/<package>/os-macos-30d-non-ci.json) [![windows](https://img.shields.io/endpoint?url=https://pypi-badges.intfar.com/<package>/os-windows-30d-non-ci.json)](https://pypi-badges.intfar.com/<package>/os-windows-30d-non-ci.json)
```

Replace `<package>` with the actual package name in each block.

- [ ] **Step 3: Add "By OS breakdown" paragraph to "What these badges actually count" section**

Find the "Per-installer breakdown" paragraph and insert after it:

```markdown
**By OS breakdown.** Each per-OS badge applies the same `details.ci != True` filter as the hero — they answer "non-CI downloads on that OS." `Darwin` is pypinfo's emission for what users call macOS; the badge filename and label use `macos`. The per-OS sum can be less than the hero count: rows whose user-agent didn't expose a system_name (or exposed one outside Linux/Darwin/Windows) drop out of the per-OS aggregation but still count toward the hero — same pattern as the per-installer-sum ≤ hero gap.
```

- [ ] **Step 4: Add 3 rows to "Use this service for your own package" table**

Find the existing table (search `grep -n 'installer-pip-' README.md | head`). Below the existing per-installer rows, add:

```markdown
| `os-linux-30d-non-ci.json`   | linux (30d)   | Per-OS, Linux            |
| `os-macos-30d-non-ci.json`   | macos (30d)   | Per-OS, macOS (Darwin)   |
| `os-windows-30d-non-ci.json` | windows (30d) | Per-OS, Windows          |
```

Match the existing table's column widths and alignment.

- [ ] **Step 5: Verify the README still renders cleanly**

```bash
uv run pytest -k readme  # if there's a README live-render test
git diff README.md | head -100
```

Inspect the diff visually — every new badge URL must point to the correct package, every new paragraph must sit in the expected location.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs(README): add per-OS dogfood badges + breakdown paragraph + table rows

Each dogfood package's block gains a 'By OS (30d, non-CI):' paragraph
parallel to the existing 'By installer' paragraph (3 badges:
linux/macos/windows). 'What these badges actually count' gains a
'By OS breakdown' paragraph documenting the per-OS-sum ≤ hero gap.
'Use this service for your own package' table grows 3 rows.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: CHANGELOG entry

**Files:**
- Modify: `CHANGELOG.md` — `## [Unreleased]` → `### Added`.

- [ ] **Step 1: Read the current Unreleased section**

```bash
head -25 CHANGELOG.md
```

The section should already contain a `### Added` block from PR #54 (the uv-lock-refresh entry) and a `### Changed` block from PRs #52/#53. The new bullet goes at the end of the `### Added` block (chronological within section).

- [ ] **Step 2: Add the bullet**

Use `Edit` to add a new bullet at the end of the `### Added` block. The bullet:

```markdown
- **Per-OS badge files (v3 OS distribution feature).** The collector now emits three additional shields.io endpoint badge JSON files per package per window: `os-linux-<N>d-non-ci.json`, `os-macos-<N>d-non-ci.json`, `os-windows-<N>d-non-ci.json`. The badge label format mirrors v2's parameterized `(Nd)` style — e.g., `linux (30d)`, `macos (30d)`, `windows (30d)`. Color logic (`blue` if count ≥ 10 else `lightgrey`) is unchanged. Pypinfo group-by extends from `ci installer` to `ci installer system` so a single BigQuery call returns both per-installer and per-system breakdowns; BigQuery cost is unchanged (same source table, marginal column). `run_pypinfo()`'s return type changes from `dict[str, int]` to a TypedDict carrying `by_installer` and `by_system` aggregates. `_health.json` per-package successful entries gain a `counts_by_system` field. `PackageOutcome` gains a `counts_by_system` attribute. Filename slug and badge label use `macos` (user-friendly); the internal allowlist key is `Darwin` to match pypinfo's raw emission. No `pyproject.toml` range changes. The v0.2.0 hero-stability invariant is preserved: hero count remains `sum(by_installer.values())` regardless of system_name; per-system aggregation applies an independent allowlist filter so rows with missing or non-allowlisted system_name drop out of the per-OS aggregates but still count toward the hero. Backwards-compat: `downloads-<N>d-non-ci.json` and the seven `installer-*` files unchanged in filename, schema, and value for any given pypinfo response. README dogfood blocks gain a "By OS" paragraph parallel to the existing "By installer" paragraph; "What these badges actually count" gains a "By OS breakdown" paragraph; "Use this service for your own package" table grows three rows. Spec: `docs/superpowers/specs/2026-04-29-os-distribution-badge-design.md`.
```

- [ ] **Step 3: Verify the diff is exactly the new bullet**

```bash
git diff CHANGELOG.md
```

Expected: one new bullet appended to the existing `### Added` block. No other changes.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs(CHANGELOG): record v3 OS distribution feature in Unreleased

Adds the per-OS-badges entry under ## [Unreleased] / ### Added,
matching the project's per-PR CHANGELOG rule and the v0.2.0 v2-feature
entry's house style.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Final verification + push

- [ ] **Step 1: Full test suite at 100% coverage**

```bash
uv run pytest --cov --cov-report=term-missing
```

Expected: all tests pass, coverage at 100% for `src/pypi_winnow_downloads/`. If a new branch isn't covered, add a test or remove the dead branch.

- [ ] **Step 2: Lint, format, type-check**

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/pypi_winnow_downloads/
```

Expected: all clean. Fix any findings.

- [ ] **Step 3: Verify branch state**

```bash
git log --oneline main..HEAD
git status -sb
```

Expected: 6 commits on `feat/os-distribution-badges` (constants, run_pypinfo multi-dim, OS badge emission, _health.json, README, CHANGELOG), clean working tree.

- [ ] **Step 4: Push branch via bot token**

```bash
GH_TOKEN_NEW="$(/home/cmeans/github.com/cmeans/claude-dev/github-app/get-token.sh 2>/dev/null)"
git push "https://x-access-token:${GH_TOKEN_NEW}@github.com/cmeans/pypi-winnow-downloads" -u feat/os-distribution-badges 2>&1 | tail -5
```

Expected: `* [new branch] feat/os-distribution-badges -> feat/os-distribution-badges`.

---

## Task 8: Open PR + Ready for QA

- [ ] **Step 1: Open the PR**

```bash
GH_TOKEN_NEW="$(/home/cmeans/github.com/cmeans/claude-dev/github-app/get-token.sh 2>/dev/null)"
GH_TOKEN="$GH_TOKEN_NEW" gh pr create \
  --base main \
  --head feat/os-distribution-badges \
  --title "feat: per-OS download breakdown badges (v3)" \
  --body "$(cat <<'EOF'
## Summary

Adds per-OS download breakdown badges (linux / macos / windows) parallel to the per-installer breakdown shipped in v0.2.0. Three new shields.io endpoint JSON files per package per window, plus README dogfood block extension and `_health.json` shape extension.

## Why

The installer-mix v2 feature surfaces *which packaging tool* users run when they install a package. The OS distribution breakdown answers a different operator question: *what platforms is this used on?* For deciding what OS matrix to test against, what platform-specific bugs to prioritize, or whether to ship a wheel for a specific OS, the OS breakdown is more decision-useful than the installer breakdown.

## How

- One pypinfo invocation per package per window (unchanged), now with `ci installer system` group-by (extended from `ci installer`). Cartesian rows ~6 → ~18 after allowlist filtering. BigQuery cost unchanged (same source table, marginal column).
- `run_pypinfo()` return type changes from `dict[str, int]` to a TypedDict carrying both `by_installer` and `by_system`.
- The v0.2.0 hero-stability invariant is preserved: hero = `sum(by_installer.values())` regardless of system_name. Per-system aggregation applies an independent allowlist filter (Linux/Darwin/Windows).
- `PackageOutcome` and `_health.json` gain a `counts_by_system` field. Existing fields preserved verbatim.
- README dogfood block grows a "By OS" paragraph; "What these badges actually count" gains a "By OS breakdown" paragraph; "Use this service for your own package" table grows 3 rows.

## What's in the diff

- `src/pypi_winnow_downloads/collector.py` — new constants, multi-dim pypinfo argv, restructured return shape, per-system aggregation, OS badge emission loop, `PackageOutcome` field, `_write_health()` extension.
- `tests/test_collector.py` — new tests for argv extension, return shape, per-system aggregation, system allowlist filter, edge cases (allowlisted installer + non-allowlisted system, missing system_name, CI filter), badge file emission, `_health.json` shape, v0.2.0 backwards-compat invariants.
- `README.md` — dogfood block extensions, breakdown paragraph, table rows.
- `CHANGELOG.md` — `## [Unreleased]` → `### Added` bullet.
- `docs/superpowers/specs/2026-04-29-os-distribution-badge-design.md` — design spec.
- `docs/superpowers/plans/2026-04-29-os-distribution-badges.md` — implementation plan.

## Cost

Zero net BigQuery cost (same source table, marginal additional column scanned). One additional badge-file-write per package per OS per run (3 file writes per package per window).

## Test plan

- [ ] Full pytest at 100% coverage on `src/`.
- [ ] `ruff check`, `ruff format --check`, `mypy` all clean.
- [ ] CI green (lint, typecheck, test, deploy-smoke).
- [ ] After merge: collector run on CT 112 emits 11 files per package per window (verify via `update-collector.sh status` or direct ls).
- [ ] Live README renders correctly with the 3 new badges showing real values.

## Release framing

Target release: **v0.3.0** — minor bump per SemVer. Additive feature; no breaking changes to v0.2.0 contracts.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: a URL printed, e.g. `https://github.com/cmeans/pypi-winnow-downloads/pull/<N>`. Capture the PR number.

- [ ] **Step 2: Apply Ready for QA label**

```bash
GH_TOKEN_NEW="$(/home/cmeans/github.com/cmeans/claude-dev/github-app/get-token.sh 2>/dev/null)"
GH_TOKEN="$GH_TOKEN_NEW" gh pr edit <PR_NUMBER> --add-label "Ready for QA"
```

- [ ] **Step 3: Wait for QA verdict**

The maintainer reviews per the project's standard QA flow. Controller relays findings to a fix-up subagent if `QA Failed`; otherwise proceeds to Task 9 on `QA Approved`.

---

## Task 9: Squash-merge after QA Approved + post-merge verification

- [ ] **Step 1: Verify mergeable state**

```bash
GH_TOKEN_NEW="$(/home/cmeans/github.com/cmeans/claude-dev/github-app/get-token.sh 2>/dev/null)"
GH_TOKEN="$GH_TOKEN_NEW" gh pr view <PR_NUMBER> --json mergeable,mergeStateStatus --jq '{mergeable, mergeStateStatus}'
```

Expected: `mergeable: MERGEABLE`, `mergeStateStatus: CLEAN`.

- [ ] **Step 2: Squash-merge**

```bash
GH_TOKEN_NEW="$(/home/cmeans/github.com/cmeans/claude-dev/github-app/get-token.sh 2>/dev/null)"
GH_TOKEN="$GH_TOKEN_NEW" gh pr merge <PR_NUMBER> --squash \
  --subject "feat: per-OS download breakdown badges (v3) (#<PR_NUMBER>)" \
  --body "Adds per-OS badge files (linux/macos/windows) parallel to the per-installer breakdown shipped in v0.2.0. Pypinfo group-by extended from ci installer to ci installer system; run_pypinfo() return type restructured to a TypedDict carrying both by_installer and by_system; PackageOutcome and _health.json gain counts_by_system; README dogfood block grows a By OS paragraph. v0.2.0 hero-stability invariant preserved.

Closes #<PR_NUMBER>."
```

- [ ] **Step 3: Sync local main**

```bash
git checkout main
git pull --ff-only
git log --oneline -3
```

Expected: most recent commit is the squashed merge.

- [ ] **Step 4: Delete local feature branch**

```bash
git branch -D feat/os-distribution-badges
```

- [ ] **Step 5: Wait for next collector run on CT 112 (or trigger manually)**

The collector runs daily on CT 112 via systemd timer. Either wait for the next scheduled run, or trigger immediately:

```bash
ssh holodeck pct exec 112 -- systemctl start pypi-winnow-downloads-collector.service
```

(Use `.deploy/scripts/update-collector.sh update main` to also pick up the new code; otherwise the deployed wheel is still 0.2.0 and won't emit the new files until v0.3.0 is published or a tarball install pulls main.)

- [ ] **Step 6: Verify the new files exist**

```bash
ssh holodeck pct exec 112 -- ls /var/lib/pypi-winnow-downloads/output/<package>/ | sort
```

Expected: 11 files per package — the original 8 plus 3 new `os-*.json`. `_health.json` at the output root has `counts_by_system` per successful package.

- [ ] **Step 7: Verify live README renders**

Open the live README in a browser. Each dogfood block should show 3 new badges (linux/macos/windows) with real values pulled from `pypi-badges.intfar.com`.

The v0.3.0 release commit + tag is a separate PR (not part of this feature plan). When ready, follow the existing release-PR pattern (bump version in `pyproject.toml`, stamp the CHANGELOG `## [Unreleased]` → `## [0.3.0] - YYYY-MM-DD`).

---

## Self-review notes (post-write)

- **Spec coverage:** Every spec section maps to a task — constants block (Task 1), pypinfo argv + return shape + aggregation (Task 2), per-system filter + edge case (Task 2), badge file emission (Task 3), `PackageOutcome` (Task 3), `_health.json` shape (Task 4), README dogfood + breakdown + table (Task 5), CHANGELOG (Task 6), test coverage including the v0.2.0 hero-stability invariant (Tasks 2–4), v0.3.0 release framing (Task 9 step 5+).
- **Placeholder scan:** No "TBD" or "implement later." `<PR_NUMBER>` placeholders in Tasks 8–9 are explicit "fill in after Step 1 prints it" markers, not unresolved scope. The tests' `_make_config` and `main(config_override=...)` calls in Task 4 are notes-to-self for the implementer to mirror the existing test harness — checked via `grep`.
- **Type / name consistency:** `_SYSTEM_NAMES`, `_SYSTEM_ALLOWLIST`, `_OS_BADGE_SPECS`, `RunPypinfoResult`, `by_installer`, `by_system`, `counts_by_system` — used consistently across tasks. Filename slug (`os-linux-Nd-non-ci.json` etc.) consistent across constants block (Task 1), badge emission (Task 3), README (Task 5), CHANGELOG (Task 6).
- **TDD discipline:** Tasks 2, 3, 4 each follow write-failing-tests → run-fail → implement → run-pass → commit. Tasks 1, 5, 6, 7 are non-TDD-natural (constants/docs/verification).
