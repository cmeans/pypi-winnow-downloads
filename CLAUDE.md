# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status: pre-implementation

As of the initial commit, the repo contains only `LICENSE`. No source, no `pyproject.toml`, no tests, no `deploy/` examples. There is nothing to build, run, or test yet. The first real change is gated on the workflow below.

## Authoritative context lives in Awareness, not in files

The design, scope, deployment target, and acceptance criteria are **not** in this repo — they are in the Awareness MCP store. Before doing anything, fetch:

- `handoff:pypi-winnow-downloads:2026-04-23:lean-v1` — the actionable summary
- `project:pypi-winnow-downloads` — the why, landscape analysis, v1 scope boundaries, future-badge backlog
- `config:gcp:pypi-winnow-downloads` — GCP project ID, service account, IAM roles, sandbox constraints
- `secret-ref:pypi-winnow-downloads:bigquery-sa-key` — credential path + handling rules (pointer only; never read the key file into conversation)

Query pattern: `get_knowledge(tags=["project:pypi-winnow-downloads"])` returns most of these in one call. Always re-read before acting — these entries get updated and the version in memory drifts.

## MANDATORY workflow: planner first, implementation second

**Do not write implementation code on the first visit.** The handoff explicitly requires a planner sub-agent to produce a design document covering module layout, config schema, collector approach (shell `pypinfo` vs library), output layout, HTTP server choice (nginx vs Caddy — the only open deployment decision), staleness detection, badge copy, license, and phased milestones. Chris must approve the plan before any code lands.

If you find yourself reaching for `Write` on a `.py` file before a plan exists and has been approved, stop.

## Deployment target is pinned — do not re-litigate

LXC container on Proxmox (Holodeck), systemd timer + service units inside the LXC. This is **resolved**, not a planner question. The repo ships deployment *examples* under `deploy/` (systemd units, nginx-or-Caddy config, Dockerfile) with placeholder paths — never Chris-specific paths, hostnames, or credential locations. Chris's actual LXC setup lives in his homelab, not in this repo.

## Scope discipline

This is a bounded weekend project competing for attention with mcp-awareness (pre-beta). If implementation reveals unexpected complexity that would turn it into a multi-weekend project, **stop and escalate to Chris** rather than expanding scope silently. The handoff's out-of-scope list (database, web framework, user-supplied package API, auth, backfill, web UI, additional badges) is a hard boundary.

**Terminology is load-bearing:** downloads ≠ installs ≠ usage. BigQuery measures downloads only. Badge copy and README must never promise more. See the "Downloads vs installs vs usage" section of `project:pypi-winnow-downloads`.

## License is resolved: Apache 2.0

The repo ships **Apache 2.0** and that is the final choice, not a planner question. Chris's intent is maximum free availability — AGPL v3's network-use copyleft works against that goal. Do not re-open this decision or treat the project entry's older "AGPL v3 default" language as live guidance.

## Pre-flight items Chris owns

Items 5, 6, and 7 of the pre-flight checklist are Chris's responsibility and may not be done yet when you arrive:

5. JSON credentials placed inside the LXC at the documented path
6. Public HTTPS exposure decision (Tailscale Funnel vs existing reverse proxy)
7. LXC container provisioned on Proxmox

Verify these are complete before attempting a live run, or surface clear instructions for Chris to complete them. Do not attempt to provision the LXC yourself.

## Updating awareness on completion

On release, update `project:pypi-winnow-downloads` status from "Pre-flight in progress" to "Released v1" with release date, PyPI URL, and live badge URL. Write an `acted_on` record referencing the handoff entry. Suggest a LinkedIn post draft using the project entry's post-material notes.
