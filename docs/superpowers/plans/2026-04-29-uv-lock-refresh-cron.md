# `uv-lock-refresh.yml` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a scheduled GitHub Actions workflow that periodically re-resolves `uv.lock` so transitive dependency pins stay fresh between Dependabot's advisory- and cascade-driven updates.

**Architecture:** Single new workflow file (`uv-lock-refresh.yml`). Skip-gate checks for open dep PRs. On a Thursday cron, runs `uv lock --upgrade`, gates on real diff, runs pytest against the new lockfile, then commits + opens a PR via the same App-token pattern that `dependabot-changelog.yml` uses (so downstream CI workflows fire on the bot's push).

**Tech Stack:** GitHub Actions, `actions/create-github-app-token`, `astral-sh/setup-uv@v7`, `gh` CLI, Python 3 (CHANGELOG insertion script), bash.

**Spec:** `docs/superpowers/specs/2026-04-29-uv-lock-refresh-cron-design.md`

---

## File structure

| Path | Action | Responsibility |
| --- | --- | --- |
| `docs/superpowers/specs/2026-04-29-uv-lock-refresh-cron-design.md` | Add to commit | Spec from brainstorming. Currently untracked. |
| `.github/workflows/uv-lock-refresh.yml` | Create | The cron workflow itself. Single file, ~120 lines YAML. |
| `CHANGELOG.md` | Modify | One bullet under `## [Unreleased]` → `### Added` describing the new workflow. |

---

## Task 1: Branch from main, stage the spec

**Files:**
- Add: `docs/superpowers/specs/2026-04-29-uv-lock-refresh-cron-design.md` (already exists in working tree, untracked)

- [ ] **Step 1: Create the feature branch from main**

```bash
git checkout main
git status -sb
git checkout -b chore/uv-lock-refresh-cron
```

Expected: clean working tree on main matches origin/main, then on `chore/uv-lock-refresh-cron`. The untracked spec file follows the branch (it's not committed yet, just unstaged).

- [ ] **Step 2: Verify spec file exists and is the brainstorming output**

```bash
ls -la docs/superpowers/specs/2026-04-29-uv-lock-refresh-cron-design.md
head -5 docs/superpowers/specs/2026-04-29-uv-lock-refresh-cron-design.md
```

Expected: file exists, opens with `# Weekly \`uv lock --upgrade\` cron — backstop for transitive freshness`.

No commit yet — Task 3 batches the spec, workflow, and CHANGELOG into a single commit.

---

## Task 2: Write the workflow file

**Files:**
- Create: `.github/workflows/uv-lock-refresh.yml`

- [ ] **Step 1: Create the workflow file with this exact content**

```yaml
name: uv lock refresh

# Weekly backstop for transitive dependency freshness. Runs uv lock
# --upgrade and opens a PR if the resulting uv.lock differs from main.
# Skips when a Dependabot or prior-cron PR is already open (avoid
# overlapping PRs).
#
# Pushes via a GitHub App installation token rather than
# secrets.GITHUB_TOKEN because GITHUB_TOKEN-authored pushes do NOT
# trigger downstream pull_request workflows (GitHub anti-loop policy),
# which would leave required CI checks (lint, typecheck, test,
# deploy-smoke) unsatisfied and block merge under the repo's
# main-branch ruleset. Same constraint and same fix as
# .github/workflows/dependabot-changelog.yml.
#
# Required repo secrets (already configured for dependabot-changelog.yml):
#   BOT_APP_ID         — GitHub App ID
#   BOT_APP_PRIVATE_KEY — PEM contents of the App's private key
#
# Spec: docs/superpowers/specs/2026-04-29-uv-lock-refresh-cron-design.md

on:
  schedule:
    - cron: '0 12 * * 4'   # Thursday 12:00 UTC = 07:00 America/Chicago
  workflow_dispatch:

permissions:
  contents: read
  pull-requests: read

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - name: Skip-gate — open dep PR
        id: skip-gate
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GH_REPO: ${{ github.repository }}
        run: |
          OPEN_DEP_PRS=$(gh pr list --label dependencies --label python --state open --json number --jq 'length')
          echo "Open dep PR count: $OPEN_DEP_PRS"
          if [ "$OPEN_DEP_PRS" -ne 0 ]; then
            echo "Open dep PR(s) found; deferring this week."
            echo "skip=true" >> "$GITHUB_OUTPUT"
          else
            echo "skip=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Mint GitHub App installation token
        if: steps.skip-gate.outputs.skip != 'true'
        id: app-token
        uses: actions/create-github-app-token@1b10c78c7865c340bc4f6099eb2f838309f1e8c3 # v3.1.1
        with:
          app-id: ${{ secrets.BOT_APP_ID }}
          private-key: ${{ secrets.BOT_APP_PRIVATE_KEY }}

      - name: Checkout main
        if: steps.skip-gate.outputs.skip != 'true'
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          ref: main
          token: ${{ steps.app-token.outputs.token }}
          fetch-depth: 1

      - name: Set up uv
        if: steps.skip-gate.outputs.skip != 'true'
        uses: astral-sh/setup-uv@v7

      - name: Run uv lock --upgrade
        if: steps.skip-gate.outputs.skip != 'true'
        run: uv lock --upgrade

      - name: Diff-gate — exit if uv.lock unchanged
        if: steps.skip-gate.outputs.skip != 'true'
        id: diff-gate
        run: |
          if git diff --quiet uv.lock; then
            echo "uv.lock unchanged; nothing to do."
            echo "changed=false" >> "$GITHUB_OUTPUT"
          else
            echo "uv.lock changed."
            echo "changed=true" >> "$GITHUB_OUTPUT"
            git diff --stat uv.lock
            git diff --stat uv.lock > /tmp/uv-lock-diff-stat.txt
          fi

      - name: Test gate — pytest against new lockfile
        if: steps.skip-gate.outputs.skip != 'true' && steps.diff-gate.outputs.changed == 'true'
        run: |
          uv sync --frozen --extra dev
          uv run pytest

      - name: Add CHANGELOG bullet
        if: steps.skip-gate.outputs.skip != 'true' && steps.diff-gate.outputs.changed == 'true'
        run: |
          python3 - <<'PY'
          import pathlib

          entry = (
              "- **`uv.lock`** transitive dependency pins refreshed via routine "
              "`uv lock --upgrade` resolve. Backstop for transitive bumps not yet "
              "picked up by Dependabot. No `pyproject.toml` range changes.\n"
          )

          path = pathlib.Path("CHANGELOG.md")
          text = path.read_text()
          lines = text.splitlines(keepends=True)

          # Locate `## [Unreleased]` (or `## Unreleased`).
          unreleased_idx = None
          unreleased_heading = "## [Unreleased]"
          for i, line in enumerate(lines):
              stripped = line.strip()
              if stripped == "## Unreleased" or stripped == "## [Unreleased]":
                  unreleased_idx = i
                  unreleased_heading = stripped
                  break

          if unreleased_idx is None:
              # Insert fresh Unreleased after the title.
              insert_at = 0
              for i, line in enumerate(lines):
                  if line.startswith("# "):
                      insert_at = i + 1
                      break
              new_block = ["\n", f"{unreleased_heading}\n", "\n", "### Changed\n", "\n", entry]
              lines = lines[:insert_at] + new_block + lines[insert_at:]
          else:
              # Find ### Changed between Unreleased and next ## heading.
              changed_idx = None
              end_idx = len(lines)
              for j in range(unreleased_idx + 1, len(lines)):
                  if lines[j].startswith("## "):
                      end_idx = j
                      break
                  if lines[j].strip() == "### Changed":
                      changed_idx = j
                      break
              if changed_idx is not None:
                  insert_at = changed_idx + 1
                  if insert_at < end_idx and lines[insert_at].strip() == "":
                      insert_at += 1
                  lines.insert(insert_at, entry)
              else:
                  # Insert ### Changed at the right KaC v1.1.0 position
                  # (Added → Changed → Deprecated → Removed → Fixed → Security).
                  after_changed = {"### Deprecated", "### Removed", "### Fixed", "### Security"}
                  insert_at = end_idx
                  for j in range(unreleased_idx + 1, end_idx):
                      if lines[j].strip() in after_changed:
                          insert_at = j
                          break
                  block = ["### Changed\n", "\n", entry, "\n"]
                  for k, ln in enumerate(block):
                      lines.insert(insert_at + k, ln)

          path.write_text("".join(lines))
          print("Inserted CHANGELOG entry.")
          PY

      - name: Commit, push branch, open PR
        if: steps.skip-gate.outputs.skip != 'true' && steps.diff-gate.outputs.changed == 'true'
        env:
          GH_TOKEN: ${{ steps.app-token.outputs.token }}
          GH_BOT_USER_ID: '272174644'
        run: |
          DATE=$(date -u +%Y-%m-%d)
          BRANCH="chore/uv-lock-refresh-$DATE"
          git config user.name "cmeans-claude-dev[bot]"
          git config user.email "${GH_BOT_USER_ID}+cmeans-claude-dev[bot]@users.noreply.github.com"
          git checkout -b "$BRANCH"
          git add uv.lock CHANGELOG.md
          git commit -m "chore(deps): refresh uv.lock transitive pins ($DATE)"
          git push -u origin "$BRANCH"

          DIFF_STAT=$(cat /tmp/uv-lock-diff-stat.txt)
          {
            echo "## Summary"
            echo
            echo "Routine \`uv lock --upgrade\` refresh — backstop for transitive dependency bumps that haven't yet been picked up by Dependabot's advisory- or cascade-driven flow."
            echo
            echo "- No \`pyproject.toml\` range changes."
            echo "- Test suite passed against the new lockfile (test gate before PR opened)."
            echo "- This is the cron in \`.github/workflows/uv-lock-refresh.yml\` — see spec at \`docs/superpowers/specs/2026-04-29-uv-lock-refresh-cron-design.md\`."
            echo
            echo "## Diff stat"
            echo
            echo '```'
            echo "$DIFF_STAT"
            echo '```'
            echo
            echo "## Test plan"
            echo
            echo "- [x] \`uv sync --frozen --extra dev && uv run pytest\` passes (test gate)."
            echo "- [ ] CI green on PR head."
            echo "- [ ] No \`pyproject.toml\` lines changed (verify in Files tab)."
            echo
            echo "🤖 Generated by uv-lock-refresh.yml"
          } > /tmp/uv-lock-pr-body.md

          gh pr create \
            --base main \
            --head "$BRANCH" \
            --title "chore(deps): refresh uv.lock transitive pins ($DATE)" \
            --body-file /tmp/uv-lock-pr-body.md \
            --label "dependencies" \
            --label "python" \
            --label "Ready for QA"
```

- [ ] **Step 2: Lint with `yamllint`**

```bash
yamllint .github/workflows/uv-lock-refresh.yml
```

Expected: no errors. The repo doesn't have a `.yamllint` config so default rules apply; standard YAML errors (unparseable, indent inconsistencies) would surface here.

- [ ] **Step 3: Lint with `actionlint`**

```bash
uvx --from actionlint-py actionlint .github/workflows/uv-lock-refresh.yml; echo "exit=$?"
```

Expected: exit 0, no output. `actionlint` validates GitHub Actions syntax (event triggers, step ordering, expression syntax, action references) — catches things `yamllint` can't.

- [ ] **Step 4: Verify the workflow file size and structure**

```bash
wc -l .github/workflows/uv-lock-refresh.yml
grep -c '^      - name:' .github/workflows/uv-lock-refresh.yml
```

Expected: ~155–170 lines total; 8 named steps (skip-gate, mint token, checkout, setup uv, run uv lock, diff-gate, test gate, add CHANGELOG, commit/push/PR — wait, count is 9 with the test gate).

Actually the count should be 9: skip-gate, mint App token, checkout main, set up uv, run uv lock --upgrade, diff-gate, test gate, add CHANGELOG bullet, commit/push/PR. So `grep -c '^      - name:'` should return 9.

- [ ] **Step 5: Stage the new workflow file**

```bash
git add .github/workflows/uv-lock-refresh.yml
git status -sb
```

Expected: `chore/uv-lock-refresh-cron`, 1 staged file (`A  .github/workflows/uv-lock-refresh.yml`), 1 untracked file (the spec doc — Task 3 stages it).

No commit yet — Task 3 batches everything into one commit.

---

## Task 3: Add CHANGELOG entry, stage the spec, commit, push

**Files:**
- Modify: `CHANGELOG.md` — one bullet under `## [Unreleased]` → `### Added`

- [ ] **Step 1: Read the current `CHANGELOG.md` head**

```bash
head -20 CHANGELOG.md
```

Expected: `## [Unreleased]` at line 8, then a `### Changed` block at line 10 (added by PRs #52 and #53 earlier today). The new bullet goes in a new `### Added` block ABOVE `### Changed` to satisfy KaC v1.1.0 ordering (Added → Changed → ...).

- [ ] **Step 2: Add the `### Added` block**

Use `Edit` to replace:
```
## [Unreleased]

### Changed
```
with:
```
## [Unreleased]

### Added

- **`.github/workflows/uv-lock-refresh.yml`** new scheduled workflow runs `uv lock --upgrade` every Thursday 12:00 UTC as a backstop for transitive dependency freshness — picks up minor/patch bumps that Dependabot's advisory- and cascade-driven flow hasn't yet surfaced. Skip-gate defers the run if a `dependencies` + `python`-labeled PR is already open (Dependabot mid-cycle or prior cron PR pending QA), so PRs don't overlap. Test gate (`uv sync --frozen --extra dev && uv run pytest`) blocks PR creation if the new lockfile breaks the suite. PR is opened via the existing `cmeans-claude-dev[bot]` App token (same path as `dependabot-changelog.yml`) so downstream CI checks (lint, typecheck, test, deploy-smoke) fire on the bot's push and don't leave the merge gate stuck. Most weeks: no PR (Dependabot already covered transitives via cascade). Spec: `docs/superpowers/specs/2026-04-29-uv-lock-refresh-cron-design.md`.

### Changed
```

- [ ] **Step 3: Verify the CHANGELOG diff is exactly the intended addition**

```bash
git diff CHANGELOG.md
```

Expected: 4 added lines (the `### Added` heading line, blank line, the bullet, and a trailing blank line). No changes to other parts of the file.

- [ ] **Step 4: Stage the CHANGELOG and the spec file**

```bash
git add CHANGELOG.md docs/superpowers/specs/2026-04-29-uv-lock-refresh-cron-design.md
git status -sb
```

Expected: branch `chore/uv-lock-refresh-cron`, 3 files staged (`A` workflow, `A` spec, `M` CHANGELOG). Nothing else.

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
ci: add weekly uv lock --upgrade refresh cron

New scheduled workflow .github/workflows/uv-lock-refresh.yml runs every
Thursday at 12:00 UTC as a backstop for transitive dependency freshness.
Picks up routine minor/patch bumps in the resolved lockfile that
Dependabot's advisory- and cascade-driven flow doesn't surface on its
own cadence. Skip-gates if a dep PR is already open; test-gates with
pytest against the new lockfile before opening a PR. Pushes via the
existing cmeans-claude-dev[bot] App token (same pattern as
dependabot-changelog.yml) so downstream CI checks fire on the bot's
push and the merge gate isn't left stuck.

Spec: docs/superpowers/specs/2026-04-29-uv-lock-refresh-cron-design.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit succeeds; `git log --oneline -1` shows the commit subject.

- [ ] **Step 6: Push the branch via the bot token (mint fresh, embed in URL)**

```bash
GH_TOKEN_NEW="$(/home/cmeans/github.com/cmeans/claude-dev/github-app/get-token.sh 2>/dev/null)"
git push "https://x-access-token:${GH_TOKEN_NEW}@github.com/cmeans/pypi-winnow-downloads" -u chore/uv-lock-refresh-cron 2>&1 | tail -5
```

Expected: `* [new branch] chore/uv-lock-refresh-cron -> chore/uv-lock-refresh-cron`.

If `Invalid username or token`, the bot token is stale — re-run `get-token.sh` and retry.

---

## Task 4: Open PR + wait for CI

**Files:** None — GitHub side only.

- [ ] **Step 1: Open the PR**

```bash
GH_TOKEN_NEW="$(/home/cmeans/github.com/cmeans/claude-dev/github-app/get-token.sh 2>/dev/null)"
GH_TOKEN="$GH_TOKEN_NEW" gh pr create \
  --base main \
  --head chore/uv-lock-refresh-cron \
  --title "ci: add weekly uv lock --upgrade refresh cron" \
  --body "$(cat <<'EOF'
## Summary

Adds a new scheduled GitHub Actions workflow (`.github/workflows/uv-lock-refresh.yml`) that runs every Thursday at 12:00 UTC as a backstop for transitive dependency freshness — picks up minor/patch bumps that Dependabot's advisory- and cascade-driven flow doesn't surface on its own.

## Why

Dependabot's `pip` ecosystem already handles direct deps in `pyproject.toml` and the corresponding `uv.lock` entries on a Monday cadence. What it doesn't routinely do is a "re-resolve everything to latest compatible within ranges" pass on a fixed cadence. Transitives can drift several patch releases behind upstream during quiet stretches.

This cron closes the gap. Most weeks it produces no PR (Dependabot's cascade already covered everything); occasional weeks it surfaces a transitive bump that would otherwise have stayed stale.

## How

- **Skip-gate** — exits 0 (no PR) when a `dependencies`+`python`-labeled PR is already open (Dependabot mid-cycle, or prior cron PR pending QA).
- **Diff-gate** — exits 0 if `uv lock --upgrade` produces no `uv.lock` change.
- **Test gate** — `uv sync --frozen --extra dev && uv run pytest`. PR creation is blocked if tests fail against the new lockfile.
- **App token push** — same pattern as `dependabot-changelog.yml`. `GITHUB_TOKEN` pushes don't trigger downstream `pull_request` workflows; using the App token ensures required CI checks fire on the bot's push.
- **CHANGELOG bullet** — added inline by the workflow's Python script (mirrors the insertion logic in `dependabot-changelog.yml`).

## Cost

Zero. Public repo → unlimited GitHub Actions minutes. ~30s/week when no diff, ~2-3 min when there is one.

## Test plan

- [ ] `yamllint .github/workflows/uv-lock-refresh.yml` clean (verified locally).
- [ ] `actionlint .github/workflows/uv-lock-refresh.yml` clean (verified locally).
- [ ] CI green on this PR's CI run (lint, typecheck, test, deploy-smoke).
- [ ] After merge: manual `workflow_dispatch` to verify end-to-end behavior in at least one mode (skip-gate triggered if a Dependabot PR is open, or normal flow if not).

## Spec

`docs/superpowers/specs/2026-04-29-uv-lock-refresh-cron-design.md` (committed in this PR).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: a URL printed, e.g. `https://github.com/cmeans/pypi-winnow-downloads/pull/54`. Capture the PR number.

- [ ] **Step 2: Mark Ready for QA**

```bash
gh pr edit <PR_NUMBER> --add-label "Ready for QA"
```

Replace `<PR_NUMBER>` with the captured number.

- [ ] **Step 3: Wait for QA approval**

The maintainer reviews per the project's standard QA flow (`Ready for QA → QA Active → QA Approved` labels). When QA Approved, controller proceeds to merge.

If QA Failed, controller relays findings to a fix-up subagent.

---

## Task 5: Merge + cleanup

**Files:** None — GitHub + local sync.

- [ ] **Step 1: Squash-merge**

```bash
GH_TOKEN_NEW="$(/home/cmeans/github.com/cmeans/claude-dev/github-app/get-token.sh 2>/dev/null)"
GH_TOKEN="$GH_TOKEN_NEW" gh pr merge <PR_NUMBER> --squash \
  --subject "ci: add weekly uv lock --upgrade refresh cron (#<PR_NUMBER>)" \
  --body "Backstop for transitive dependency freshness — runs every Thursday at 12:00 UTC. Skip-gates if a dep PR is open; test-gates with pytest against the new lockfile; pushes via the existing cmeans-claude-dev[bot] App token so downstream CI fires.

Closes #<PR_NUMBER>."
```

- [ ] **Step 2: Sync local main**

```bash
git checkout main
git pull --ff-only
git log --oneline -3
```

Expected: most recent commit is the squashed merge of this PR.

- [ ] **Step 3: Delete local feature branch**

```bash
git branch -D chore/uv-lock-refresh-cron
```

(Force-delete because the branch wasn't merged into local main from git's perspective — squash-merge produced a different commit.)

The remote branch is auto-deleted by GitHub on PR merge.

---

## Task 6: Smoke-test via `workflow_dispatch`

**Files:** None — GitHub Actions side only.

- [ ] **Step 1: Manually trigger the workflow**

```bash
GH_TOKEN_NEW="$(/home/cmeans/github.com/cmeans/claude-dev/github-app/get-token.sh 2>/dev/null)"
GH_TOKEN="$GH_TOKEN_NEW" gh workflow run uv-lock-refresh.yml
```

Expected: `✓ Created workflow_dispatch event for uv-lock-refresh.yml at main`.

- [ ] **Step 2: Watch the run**

```bash
sleep 5
GH_TOKEN_NEW="$(/home/cmeans/github.com/cmeans/claude-dev/github-app/get-token.sh 2>/dev/null)"
GH_TOKEN="$GH_TOKEN_NEW" gh run list --workflow uv-lock-refresh.yml --limit 1
```

Expected: a run is `queued` or `in_progress`. After ~30s–2 min it should be `completed` with conclusion `success`.

- [ ] **Step 3: Verify outcome**

Two acceptable end states:

  - **Skip-gate path:** if a Dependabot or other `dependencies`+`python`-labeled PR is open at trigger time, the workflow logs "Open dep PR(s) found; deferring this week." and exits 0. No new PR.
  - **No-diff path:** no open dep PRs, but `uv lock --upgrade` produces no diff. Workflow logs "uv.lock unchanged; nothing to do." and exits 0. No new PR.
  - **PR-opened path:** `uv lock --upgrade` produces a diff, tests pass, and a `chore/uv-lock-refresh-YYYY-MM-DD` PR is opened with `dependencies`, `python`, and `Ready for QA` labels.

Inspect the run logs:
```bash
gh run view --log <RUN_ID>  | tail -40
```

For the skip-gate path, look for `skip=true` in the GITHUB_OUTPUT line. For the no-diff path, look for `uv.lock unchanged`. For the PR-opened path, look for the `gh pr create` final URL.

- [ ] **Step 4: If a PR was opened, sanity-check it**

```bash
gh pr list --label dependencies --state open --json number,title,labels,headRefName
```

Expected: a row with `chore/uv-lock-refresh-YYYY-MM-DD` head, three labels, recent date suffix.

If the PR looks reasonable (sane lockfile diff, test gate passed, CHANGELOG bullet present, no stray `pyproject.toml` changes), the cron is verified and ready for the QA flow. Treat it like any other dep PR.

If something looks off (PR opened with broken lockfile, missing CHANGELOG bullet, wrong labels, etc.), the workflow itself has a bug — open a follow-up issue describing the symptom and either revert or fix forward.

---

## Self-review notes (post-write)

- **Spec coverage:** Every spec section has a task — workflow file (Task 2), CHANGELOG entry (Task 3), App-token auth (in Task 2's workflow content), skip-gate (Task 2), diff-gate (Task 2), test gate (Task 2), inline CHANGELOG bullet (Task 2), PR creation with the right labels (Task 2), spec file committed alongside (Task 3), QA flow integration (Task 4), smoke verification (Task 6).
- **Placeholder scan:** No "TBD" or "implement later." `<PR_NUMBER>` placeholders in Tasks 4–5 are explicit "fill in after Step 1 prints it" markers, not unresolved scope.
- **Type / name consistency:** `uv-lock-refresh.yml` filename, `chore/uv-lock-refresh-cron` PR branch, `chore/uv-lock-refresh-YYYY-MM-DD` cron-generated branches — naming is internally consistent. Workflow file name matches the path used in `gh workflow run` (Task 6).
- **Pre-existing automation interaction:** `dependabot-changelog.yml` is gated to `dependabot[bot]` author, so it does NOT fire on cron's PR. `qa-gate.yml` fires on the `Ready for QA` label, which the workflow applies. `pr-labels.yml` and `pr-labels-ci.yml` fire on PR events as usual. No special-casing required.
