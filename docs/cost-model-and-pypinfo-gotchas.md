# Cost model and pypinfo CLI gotchas

This is an engineering note for anyone running `pypi-winnow-downloads`
themselves, or anyone hacking on the `collector.py` BigQuery code path.
It captures two things that are non-obvious from the code alone:

1. The shape of BigQuery scan cost for `bigquery-public-data.pypi.file_downloads`
2. Two foot-guns in `pypinfo`'s CLI that affect how the collector calls it

The numbers in the cost section come from empirical testing during PR #14
(batched-query refactor, ultimately closed in favor of the per-package
serial approach this repo ships). The pypinfo gotchas were surfaced
during that same testing and during the v0.1.x feat/collector PR review
cycles.

## BigQuery scan cost shape

`bigquery-public-data.pypi.file_downloads` is clustered on `file.project`
(or has clustering-equivalent block layout). Clustering means a query
filtering on a single project efficiently prunes to that project's
blocks; a query filtering on N projects via `WHERE file.project IN (...)`
scans all N projects' blocks.

Empirical (30-day window, daily run, all installers):

| Approach                    | Bytes billed   | Per package |
|-----------------------------|----------------|-------------|
| 1 package, single query     | ~4.6 GB        | 4.6 GB      |
| 300 packages, batched query | ~2.32 TB       | ~7.7 GB/pkg |
| 300 packages, serial calls  | ~1.38 TB       | ~4.6 GB/pkg |

**Batching is more expensive than serial**, not less. The cluster-pruning
advantage applies most cleanly to single-package queries, so a tight
loop of 1-package queries comes out ahead of a single big `WHERE IN`.
Bytes billed is roughly proportional to packages-touched regardless of
batching strategy.

### Cost envelope at the per-package serial rate (~4.6 GB/pkg/run)

| Packages | Monthly bytes billed | Free tier (1 TB/mo) ceiling |
|----------|----------------------|-----------------------------|
| 4        | 552 GB               | comfortably under            |
| 7        | 966 GB               | at the ceiling               |
| 10       | 1.38 TB              | ~$2/month over               |
| 50       | 6.9 TB               | ~$30/month                   |
| 100      | 13.8 TB              | ~$65/month                   |
| 300      | 41 TB                | ~$200/month                  |

After-free-tier rate: $5/TB.

The `BigQuery Sandbox` mode this project's GCP setup uses returns quota
errors (not charges) when the free tier is exhausted. That is the
desired failure mode for a hobby workload: "stop emitting badges" beats
"silently bill the maintainer's credit card."

### Levers for scale, in order of effectiveness

1. **Reduce collection frequency.** Daily → weekly is a 7x cost cut;
   daily → monthly is 30x. Trades freshness for cost; for download
   counts averaged over a 30-day window, freshness within a few days
   is plenty.
2. **Use pypistats.org as the data source instead.** Free, no scan
   cost, but loses the installer-mirror filtering refinement that this
   project's "non-CI downloads" framing depends on. You're back to
   the v1 mirror-inclusive numbers we explicitly improved on.
3. **Hybrid:** pypistats daily for rough counts, BigQuery weekly for
   installer-mix sanity. Best cost-vs-quality tradeoff at scale.
4. **Materialized view of pre-aggregated daily summaries.** Significant
   setup, modest savings, only worth it past hundreds of packages.

### Levers that do NOT help cost

- Direct BigQuery client library (skip the `pypinfo` subprocess) — the
  scan cost is the same. Only saves subprocess startup time (~100 ms).
- Smaller batch sizes (e.g., 10 packages at a time vs. 300) — total
  scan cost is roughly proportional to packages-touched.
- Sample-based scans (`TABLESAMPLE`) — introduces noise. Bad for the
  honesty pitch this project makes about its numbers.

### Decision for v1

Per-package serial is the right shape for current scale (4 dogfood
packages, comfortably under the free tier) and remains reasonable at
~10-20 packages. Beyond that, the levers above are the lever — not
query batching. PR #14's batched-query refactor was closed for that
reason.

## pypinfo CLI gotchas

These are documented at `pypinfo/cli.py` and `pypinfo/core.py` line
ranges as of the version this project pins (`pypinfo>=23.0.0`). They
are surprising enough that anyone editing `run_pypinfo`'s argv
construction should know about them.

### 1. `--where` AND-combines with the positional, never overrides it

`pypinfo [PROJECT] [FIELDS...]` always generates a `WHERE
file.project = "<PROJECT>"` clause from the positional and ANDs it with
any additional `--where` predicate. It does not replace one with the
other. Source, `pypinfo/core.py:build_query`:

```python
conditions = ["WHERE timestamp BETWEEN ..."]
if project:
    conditions.append(f'file.project = "{project}"\n')
...
query += "  AND ".join(conditions)
if where:
    query += f"  AND {where}\n"
```

The `if project:` check means an **empty-string positional** (`""`)
skips the auto-filter. So if you ever want a multi-package query, the
positional must be `""` and the package list goes in `--where`:

```
pypinfo --where 'file.project IN ("a","b","c")' "" project ci installer
```

Anything else and the SQL ends up with both `file.project = "a" AND
file.project IN (...)`, which silently restricts the response to
package `a` only.

This project ships per-package serial (one query per package), so the
collector passes the real package name as the positional and does not
use `--where`. The gotcha is preserved here for anyone reviving the
batched path or hacking on a fork.

### 2. `--limit` defaults to 10; falsy values fall back to that default

`limit = limit or DEFAULT_LIMIT` in `core.build_query`, with
`DEFAULT_LIMIT = 10`. Passing `--limit 0` is treated as falsy and
falls back to 10. There is no "no-limit" mode in the CLI.

For multi-pivot queries — e.g., `[PROJECT] ci installer system` —
the result has up to one row per distinct `(ci, installer, system)`
combination. Realistic combos for one package run to a few dozen, so
the default of 10 silently truncates the long tail.

In `run_pypinfo` we pivot by `ci × installer × system` (3 fields), so
the argv carries an explicit `--limit 500` to leave several-multiple
headroom over the realistic combo ceiling. SQL `LIMIT` is applied
after aggregation, so a generous bound does not change `bytes_billed`.

If you ever extend the pivot — adding `country` or `version` —
recompute the combo ceiling and bump `--limit` accordingly.

## See also

- `src/pypi_winnow_downloads/collector.py` — the live `run_pypinfo`
  function with both gotchas commented at their respective line ranges
  inside the function body.
- `tests/test_collector.py::test_run_pypinfo_argv_passes_explicit_limit`
  — regression coverage that fails if `--limit` is dropped from argv.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing#analysis_pricing)
  — the $5/TB on-demand rate referenced above.
- [pypinfo](https://github.com/ofek/pypinfo) — upstream source, where
  the file/line references in this doc point.
