# Weekly `uv lock --upgrade` cron — backstop for transitive freshness

**Status:** Draft, brainstorming-approved 2026-04-29
**Goal:** Add a scheduled GitHub Actions workflow that periodically re-resolves `uv.lock` so transitive dependency pins stay fresh between Dependabot's advisory- and cascade-driven updates.

## Why

Dependabot is already configured (`.github/dependabot.yml`) for the `pip` ecosystem on a weekly Monday cadence and grouped into a single PR per week. It updates direct deps in `pyproject.toml` and the corresponding `uv.lock` entries, plus transitives that cascade from those direct bumps. What it does **not** routinely do is a "re-resolve everything to latest compatible within ranges" pass on a fixed cadence.

That gap is small but real. A transitive (e.g., `urllib3`, `google-auth`) can ship multiple patch releases in a quiet stretch where no direct dep changes; Dependabot may not propose those changes until an advisory or cascade triggers. Over months this lets the lockfile drift several patch releases behind upstream.

This cron closes the gap as a backstop. Most weeks it produces no PR (Dependabot's cascade already covered everything); occasional weeks it surfaces a transitive bump that would otherwise have stayed stale.

## Out of scope (explicit)

- Replacing Dependabot. Dependabot remains the primary update mechanism.
- Auto-merging the cron's PR. It goes through the same `Ready for QA → QA Approved → squash-merge` flow as everything else.
- Updating `pyproject.toml` ranges. `uv lock --upgrade` re-resolves within existing ranges; range bumps stay manual.
- Slack/email alerting. CI failure email is sufficient.
- Grouping by category. The PR diff is whatever uv resolves; one flat PR.
- Coordination with the GitHub Actions and Docker Dependabot ecosystems. Those remain Dependabot-only.

## Workflow file

`.github/workflows/uv-lock-refresh.yml` — new workflow alongside `dependabot-changelog.yml`.

## Triggers

```yaml
on:
  schedule:
    - cron: '0 12 * * 4'   # Thursday 12:00 UTC = 07:00 America/Chicago
  workflow_dispatch:
```

Thursday is two days after Dependabot's Monday slot, giving the weekly Dependabot PR time to merge before the cron runs and reducing PR-overlap risk. `workflow_dispatch` enables manual ad-hoc triggering from the Actions UI for testing or one-off refreshes.

## Job flow

1. **Skip-gate — open dep PR.** Run `gh pr list --label dependencies --label python --state open --json number --jq 'length'`. If the count is non-zero, log a message and exit successfully (status 0). The query catches both Dependabot's pending weekly PR and any previous cron PR that hasn't merged yet. Either case is a reason to defer: don't open a second overlapping PR.
2. **Checkout main.** `actions/checkout` SHA-pinned to match the SHA used in `dependabot-changelog.yml` (currently `de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2`), with `ref: main` and the App token.
3. **Install uv.** `astral-sh/setup-uv@v7` (matches the rest of the repo's workflows: `ci.yml`, `publish.yml`, `test-publish.yml`). Caches uv's resolver index.
4. **Run the upgrade.** `uv lock --upgrade`. This re-resolves within `pyproject.toml` ranges and updates `uv.lock` in place.
5. **Diff-gate.** `git diff --quiet uv.lock`. Exit 0 if no changes — most weeks land here, no PR opened.
6. **Test gate.** `uv sync --frozen --extra dev` then `uv run pytest`. Must pass against the new lockfile. If it fails, the workflow exits non-zero (CI failure email alerts the maintainer); no PR is opened with a known-broken lockfile.
7. **Add a CHANGELOG bullet.** Append a one-line bullet under `## [Unreleased]` → `### Changed`, mirroring the project's per-PR CHANGELOG rule:
   > **`uv.lock`** transitive dependency pins refreshed via routine `uv lock --upgrade` resolve. Backstop for transitive bumps not yet picked up by Dependabot. No `pyproject.toml` range changes.
8. **Open the PR.**
   - Branch name: `chore/uv-lock-refresh-YYYY-MM-DD` (date suffix avoids stale-branch collisions).
   - Commit message: `chore(deps): refresh uv.lock transitive pins (YYYY-MM-DD)`.
   - PR title: same as the commit subject.
   - PR body: includes the `git diff --stat uv.lock` output (captured before the CHANGELOG amend) and notes that this is a backstop refresh, complementary to Dependabot, and that no `pyproject.toml` ranges changed.
   - Labels: `dependencies`, `python`, `Ready for QA`.
9. **Hand off to QA flow.** The `Ready for QA` label triggers the existing `qa-gate.yml` flow. The cron's PR enters the standard QA cycle.

## Auth model

**App token (`cmeans-claude-dev[bot]`) for the push, default `GITHUB_TOKEN` for the skip-gate query and uv tooling.**

Pushes authenticated with `GITHUB_TOKEN` do NOT trigger downstream `pull_request` workflows (GitHub's anti-loop policy). The repo's main-branch ruleset requires `lint`, `typecheck`, `test`, and `deploy-smoke` checks — pushes via `GITHUB_TOKEN` would leave those checks pending and block merge. The same constraint applies to `dependabot-changelog.yml`, which solves it the same way.

Concretely:

1. Mint an App installation token at job start via `actions/create-github-app-token`. Pinned by SHA, matching `dependabot-changelog.yml`'s pin discipline.
2. Use that token for `git push` and `gh pr create`.
3. Use default `GITHUB_TOKEN` for the read-only skip-gate query (`gh pr list`).

Required repo secrets (already configured for `dependabot-changelog.yml`):

- `BOT_APP_ID` — GitHub App ID
- `BOT_APP_PRIVATE_KEY` — PEM contents of the App's private key

Workflow `permissions` block:

```yaml
permissions:
  contents: read       # default token only reads; App token does the writes
  pull-requests: read
```

The App token's installation grants the broader write permissions; the workflow-level `permissions` block stays minimal.

## Loop guard

The workflow only opens new PRs on `schedule` and `workflow_dispatch` triggers — neither fires on its own bot's pushes — so the loop guard from `dependabot-changelog.yml` (which runs on `pull_request_target` and could re-trigger on its own commits) is not strictly needed here. A `concurrency: group: uv-lock-refresh` declaration serializes same-day runs (e.g., a manual `workflow_dispatch` trigger landing while the scheduled run is mid-flight) so two parallel jobs never compute the same dated branch and race on push or PR-create.

## Coordination with existing automation

| System | Trigger | Scope | Interaction with this cron |
| --- | --- | --- | --- |
| Dependabot (`pip`) | Mondays 06:00 CT | Direct + cascade in pyproject.toml + uv.lock | Cron skip-gates if Dependabot PR is open; otherwise complements via transitive backstop |
| `dependabot-changelog.yml` | `pull_request_target` + author == `dependabot[bot]` | Auto-add CHANGELOG bullet | Author-gated — does NOT fire on cron's PR. Cron adds its own CHANGELOG bullet inline. |
| `qa-gate.yml` | Label `Ready for QA` | QA workflow | Cron's PR enters the standard QA flow |
| `pr-labels.yml` / `pr-labels-ci.yml` | PR events | Label automation around CI status | No interaction needed |

## Cost

Zero dollars. `pypi-winnow-downloads` is a public repo, so GitHub Actions minutes are unlimited. The workflow does not call any paid API. ~30s/week when no diff; ~2–3 min/week when there is one (resolve + pytest). Most weeks: no PR at all.

## Test plan

- After merge, manually trigger via `workflow_dispatch` once to confirm the workflow runs end-to-end.
- Verify the skip-gate behavior by triggering manually while Dependabot has an open weekly PR — the workflow should log the skip reason and exit 0 with no PR.
- After Dependabot's next merge, manually trigger again to confirm it can produce an actual PR (or no-op if uv has nothing fresh to resolve).
- Verify the test-gate behavior by intentionally introducing an incompatible direct-dep range, confirming the workflow fails before opening a PR, then reverting.

## Acceptance criteria

- The workflow runs on the cron schedule without manual intervention.
- A Thursday run with Dependabot mid-cycle exits 0 and opens no PR.
- A Thursday run with a clean main and fresh transitives produces a PR labeled `dependencies` + `python` + `Ready for QA`, with a `git diff --stat` summary in the body.
- The PR's CHANGELOG entry is added inline by the workflow itself (under `## [Unreleased]` → `### Changed`). The existing `dependabot-changelog.yml` is author-gated to `dependabot[bot]` and does not fire on this cron's PRs, so the cron uses its own copy of the same KaC-aware insertion logic.
- A test failure against the new lockfile prevents the PR from opening.

## Implementation file list

- Create: `.github/workflows/uv-lock-refresh.yml` — the workflow itself.
- Modify: `CHANGELOG.md` — one bullet under `## [Unreleased]` → `### Added` announcing the new workflow (per project's per-PR CHANGELOG rule). Distinct from the runtime CHANGELOG bullets the workflow inserts into future PRs (those land under `### Changed`).
- No changes to `pyproject.toml`, `uv.lock`, or other existing workflows.
