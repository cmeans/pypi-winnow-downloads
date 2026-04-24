# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Implementation in progress against milestones M1–M6 defined in the planner's design doc. As of this writing:

- Project scaffold, config module (`pypi_winnow_downloads.config`), badge module (`pypi_winnow_downloads.badge`), and stub `__main__` entry point are in place with tests.
- CI/QA workflows and label automation are ported from `cmeans/mcp-clipboard` (PR #2 at the time of writing).
- Deployment infrastructure (LXC CT 112 on Proxmox, Caddy config target, DDNS via ddclient, router port-forwards) is provisioned but the service is not yet deployed.
- Remaining work: collector module (`pypinfo` subprocess + parse), real `__main__` orchestration, `deploy/` examples, publishing workflows validation, first release.

Re-read this file's "Status" section on return; older versions of this doc described the repo as pre-implementation and that framing is stale.

## Authoritative context lives in Awareness, not in files

The design, scope, deployment target, and acceptance criteria are **not** in this repo — they are in the Awareness MCP store. Before making decisions, fetch:

- `handoff:pypi-winnow-downloads:2026-04-23:lean-v1` — the actionable summary
- `project:pypi-winnow-downloads` — the why, landscape analysis, v1 scope boundaries, future-badge backlog
- `config:gcp:pypi-winnow-downloads` — GCP project ID, service account, IAM roles, sandbox constraints
- `secret-ref:pypi-winnow-downloads:bigquery-sa-key` — credential path + handling rules (pointer only; never read the key file into conversation)
- `decision:pypi-winnow-downloads:*` — per-decision records (license, config format, HTTPS exposure, staleness, CI publishing, changelog, awareness dual-write)
- `home-network:ip-assignment-convention` — LAN / Proxmox / DNS-server conventions
- `dns:intfar-com` — DNS provider + hosting details for the subdomain
- `er605-router-status` — home router model + port-forward UI conventions

Query pattern: `get_knowledge(tags=["project:pypi-winnow-downloads"])` returns most project entries in one call. Always re-read before acting — these entries get updated and the version in memory drifts.

## Workflow: planner-first has been satisfied; stay disciplined on subsequent work

The planner sub-agent ran, produced a design document, and Chris approved it. Decisions from that review are captured in the `decision:*` Awareness entries. For new scope or changes that deviate from those decisions, **go back to the planner rather than silently redesigning**. The planner-first rule exists to prevent drift between what was approved and what ships; re-running it for meaningful design changes is cheap.

If you find yourself reaching for `Write` on a `.py` file that introduces behavior outside what the design doc covers, stop and either ask or re-plan.

## Deployment target is pinned — do not re-litigate

LXC container on Proxmox (Holodeck), CT 112 at `192.168.200.112`, Debian 13 Trixie, systemd timer + service units inside the LXC. HTTP fronting via Caddy. Public DNS at `pypi-badges.intfar.com` (ZoneEdit, DDNS via `ddclient` in the LXC). Router port-forwards 80/443 to CT 112.

The repo ships deployment *examples* under `deploy/` (systemd units, Caddy config, Dockerfile) with placeholder paths. Never Chris-specific paths, hostnames, or credential locations in the repo. Chris's actual LXC setup is his homelab, not the repo.

## Scope discipline

Bounded weekend project competing for attention with mcp-awareness (pre-beta). If implementation reveals unexpected complexity that would turn it into a multi-weekend project, **stop and escalate to Chris** rather than expanding scope silently. The handoff's out-of-scope list (database, web framework, user-supplied package API, auth, backfill, web UI, additional badges beyond the v1 hero) is a hard boundary.

**Terminology is load-bearing:** downloads ≠ installs ≠ usage. BigQuery measures downloads only. Badge copy and README must never promise more. See the "Downloads vs installs vs usage" section of `project:pypi-winnow-downloads`.

## License is resolved: Apache 2.0

The repo ships **Apache 2.0** and that is the final choice, not a planner question. Chris's intent is maximum free availability — AGPL v3's network-use copyleft works against that goal. License declaration lives in `pyproject.toml` as `license = "Apache-2.0"` (PEP 639 SPDX expression); **do not add per-file `# SPDX-License-Identifier` comments** — those are the convention for AGPL/GPL projects where the per-file license claim matters legally, and are redundant noise for Apache 2.0.

## Pre-flight (historical reference)

All seven pre-flight items from the handoff are now complete:

1. ✅ GitHub repo created
2. ✅ GCP project created + BigQuery API enabled
3. ✅ Service account with `BigQuery Job User` + `BigQuery Data Viewer`
4. ✅ BigQuery-SA JSON credential generated (on Chris's workstation)
5. ✅ Public HTTPS exposure decided — Caddy + ZoneEdit subdomain + DDNS
6. ✅ Router port-forwards 80/443 → CT 112 configured
7. ✅ LXC CT 112 provisioned on Proxmox

Credential transfer into the LXC is deferred until the collector's final service user + `/etc/pypi-winnow-downloads/` directory exist (the collector PR will handle it in one direct workstation → LXC hop).

## Updating awareness on completion

On release, update `project:pypi-winnow-downloads` status to "Released v1" with release date, PyPI URL, and live badge URL. Write an `acted_on` record referencing the handoff entry. Suggest a LinkedIn post draft using the project entry's post-material notes.
