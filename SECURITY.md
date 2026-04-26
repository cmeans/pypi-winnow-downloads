# Security Policy

## Supported versions

pypi-winnow-downloads is currently on the 0.1.x line. Fixes for
security issues are applied to the latest published version only.
Users of earlier versions should upgrade.

| Version | Supported         |
| ------- | ----------------- |
| 0.1.x   | ✅ security fixes |
| < 0.1   | ❌ upgrade        |

## Reporting an issue

**Please do not file a public GitHub issue for security problems.**

The only supported channel is a **GitHub Private Security Advisory**.
To open one:

1. Go to <https://github.com/cmeans/pypi-winnow-downloads/security/advisories/new>.
2. Fill in a description, steps to reproduce, and the affected
   version.
3. Submit as a draft advisory. Only the maintainer will see it.

This creates a private thread where the report, any proof-of-concept,
the fix, and disclosure timing can be discussed without exposing the
issue publicly. The private vulnerability reporting feature is
enabled on this repository.

If you cannot use GitHub Private Security Advisories for some reason,
please open a **public** issue titled simply "Security contact
request" — no details — and the maintainer will reach out to arrange
a private channel.

## Please include

- A description of the issue and its impact.
- Steps to reproduce (or a proof-of-concept).
- The version of pypi-winnow-downloads affected.
- Your operating system and Python version (subprocess + path-handling
  behavior is OS-dependent, even though the project targets Linux for
  deployment).
- Whether the issue is reproducible against a clean
  `pip install pypi-winnow-downloads`, against a reference deploy
  (systemd / Docker), or only in a custom environment.

## What to expect

- **Acknowledgment** after the maintainer sees the report. Response
  times vary — this is a one-person project.
- **Coordinated fix timeline.** pypi-winnow-downloads is maintained by
  one person, not a security team. Please be patient.
- **Credit in the release notes** if you'd like it. Anonymous
  disclosure is also fine.
- **No monetary reward.** pypi-winnow-downloads does not operate a bug
  bounty program. Reports are voluntary contributions to project
  safety.

## Scope

**In scope**

- Argument injection or unsafe subprocess invocation when shelling out
  to `pypinfo` from `pypi_winnow_downloads.collector`.
- Path-handling issues in the badge writer that could allow a malicious
  package name in `config.yaml` to escape the configured `output_dir`
  (atomic `.tmp` + `os.replace`, parent-dir auto-creation).
- JSON-output integrity issues in the shields.io endpoint payloads
  written by the collector.
- Unsafe handling of the GCP service-account JSON credential
  (file-permission expectations; the collector's `XDG_DATA_HOME`
  isolation that prevents `pypinfo`'s persisted-credential TinyDB from
  taking priority over `GOOGLE_APPLICATION_CREDENTIALS`).
- Supply-chain or packaging issues affecting published wheels or
  sdists on PyPI (trusted publishing, sdist contents, lockfile
  integrity).
- Hardening regressions in the reference systemd unit
  (`deploy/systemd/*.service`) — for example, weakening
  `ProtectSystem`, `RestrictAddressFamilies`, or `PrivateTmp`
  directives.
- Caddyfile examples in `deploy/caddy/` that would expose the static
  badge directory more broadly than intended (default-on directory
  listings, missing `Content-Security-Policy` for JSON, etc.).

**Out of scope**

- Vulnerabilities in dependencies (`pypinfo`, `PyYAML`, `google-cloud-bigquery`,
  shields.io's badge renderer, the public BigQuery dataset itself) —
  please report those upstream to the affected project.
- Attacks that require an adversary to already have write access to
  `config.yaml`, `credential_file`, or the output directory (that's a
  compromised host, not a project-specific issue).
- BigQuery cost surprises from a misconfigured `config.yaml` (large
  `window_days`, many packages) — that's documentation territory, not
  a security issue.
- Issues with shields.io's CDN, caching, or rendering — please report
  to <https://github.com/badges/shields>.
- Issues with the BigQuery public dataset itself (data quality,
  schema changes, ingestion delays) — those are upstream to the PyPI
  Linehaul pipeline.

## Historical issues

Security-relevant findings are tracked in the GitHub issue tracker
under the `security` label. See also the [`LICENSE`](LICENSE) file
for Apache-2.0 warranty disclaimers.
