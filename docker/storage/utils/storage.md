# `storage` — IsardVDI storage utility

A unified CLI for analyzing, auditing and (optionally) cleaning up the qcow2 /
ISO / FD storage that backs IsardVDI desktops.

It runs inside the storage utils container, where the IsardVDI API and the
`/isard/` storage tree are reachable.

```
storage <subcommand> [options]
```

## Subcommand overview

| Subcommand        | Touches API state? | Touches files? | Purpose                                                              |
| ----------------- | ------------------ | -------------- | -------------------------------------------------------------------- |
| `sizes`           | reads only         | reads only     | Disk usage by storage status                                         |
| `integrity`       | reads only         | reads only     | qcow2 integrity + dependency analysis                                |
| `cleanup`         | reads only         | reads only †   | Generate categorized file lists for orphaned/broken storage          |
| `by-role`         | reads only         | reads only     | Storage grouped by user role                                         |
| `chains`          | reads only         | reads only ‡   | Backing-chain depth analysis (and optional flattening)               |
| `age-report`      | offline            | reads only     | Bucketize cleanup output by day/week/month/year                      |
| `deployments`     | reads only         | reads only     | Annotate cleanup lists with deployment ownership (`domains.tag`)     |
| `recycler-audit`  | reads only         | reads only     | Confirm whether the deployment auto-recycler is actually working     |
| `repair-chains`   | **writes**         | **writes**     | Fix broken backing chains via `qemu-img rebase`                      |
| `verify`          | **writes**         | reads          | DB-vs-disk consistency; can update DB paths and trigger `find`       |
| `recover`         | **writes**         | **writes**     | Recreate missing incremental disks for failed desktops               |
| `full-cleanup`    | **writes** §       | **writes** §   | One-shot: verify + repair + move unusable files                      |
| `db-cleanup`      | **writes** ¶       | reads only     | Detect & (with `--apply`) remove malformed `storage` rows            |
| `sparsify`        | reads/**writes**   | **writes**     | Thin wrapper over `/utils/sparsify`; flags forwarded verbatim         |

† `cleanup` is read-only **without** `--move`. With `--move` it relocates
deletable files to `/isard/volatile/to_delete/` (still no `rm`).
‡ `chains` is read-only **without** `--flatten-singles` / `--flatten-deep`,
which call `qemu-img rebase`.
§ `full-cleanup` is read-only **with** `--dry-run`. The dry-run still
writes the file lists and a `dry_run_actions.jsonl` describing every
rebase / sparsify / compress / move that would have run.
¶ `db-cleanup` reports only by default; deletes only with `--apply`,
after a y/N confirmation, and only rows that pass cross-table reference
checks.

---

## Read-only commands

These never modify API state and never delete files. Safe to run on
production at any time.

### `cleanup` — generate categorized file lists

Walks `/isard/`, classifies every qcow2/ISO/FD against the API, and writes a
timestamped report directory under `/logs/analyze/<YYYYMMDDHHMM>/`:

- `bad_*.txt` — candidates to delete (orphans, broken chains, dead artifacts)
- `ok_*.txt` — informative classifications (root images, leaves, registered
  media, …)
- `bad_db_storage_entries.jsonl` / `bad_db_media_entries.jsonl` — DB rows with
  missing fields (need DB review, **not** file deletion)
- `<name>.meta.tsv` — sidecar for every list with `path<TAB>size_bytes<TAB>mtime_iso`
  for every path that still exists on disk. Used by `age-report`.
- `README.md` — human-readable summary with size and template-count tables

```bash
storage cleanup
RUN=$(ls -1dt /logs/analyze/2* | head -1)
ls "$RUN"
```

### `age-report` — size & count distribution by date

Reads the `*.meta.tsv` sidecars and bucketizes by file `mtime`.

```bash
storage age-report "$RUN"                                # default --bucket month
storage age-report "$RUN" --bucket year
storage age-report "$RUN" --bucket week --filter bad_deletable_orphans --per-file
storage age-report "$RUN" --bucket day  --filter bad_broken_chain --filter bad_non_qcow2
```

Output (one section per `--bucket`, plus per-file when `--per-file`):

```
=== OVERALL (month) ===
bucket            count      size_GB
2024-03               2         0.00
2025-06            1124      4715.82
TOTAL              1126      4715.83
```

### `deployments` — annotate cleanup lists with deployment ownership

Resolves each path's `storage_id` (`Path(p).stem`) against the API and writes
`<list>.deployments.tsv` with columns:

```
path  storage_id  domain_id  deployment_id
```

Then prints a summary grouped by `deployment_id` (with `(unassigned)` last for
files whose storage has no domain or whose domain has `tag=None`).

```bash
storage deployments "$RUN"
storage deployments "$RUN" --per-file --filter bad_deletable_orphans
storage deployments "$RUN" --filter bad_broken_chain --filter bad_orphan_medias
```

### `recycler-audit` — is the deployment auto-recycler working?

Joins `domains.tag`, `domains.accessed`, `storages.status`, and the
`unused_item_timeout` config to detect deployments that should already have
been recycled but weren't.

Writes three TSVs (in `--output-dir` or a fresh `/logs/analyze/<TS>/`):

| File                                   | Contents                                                                  |
| -------------------------------------- | ------------------------------------------------------------------------- |
| `deployment_recycler_audit.tsv`        | Every deployment: max(accessed), months idle, storage status breakdown    |
| `deployment_recycler_violations.tsv`   | Past cutoff AND ≥1 storage still `ready` — should be empty if cron works  |
| `deployment_recycler_empty.tsv`        | `deployments` table rows with zero tagged desktops (cron's eq_join blind spot) |

```bash
# Use the cutoff configured in the admin UI:
storage recycler-audit --output-dir "$RUN"

# Override (e.g. simulate "what if we set 6 months"):
storage recycler-audit --output-dir "$RUN" --cutoff-months 6
```

Headline printed to stdout already gives the answer:

```
Configured cutoff source : unused_item_timeout.send_unused_deployments_to_recycle_bin=None
Effective cutoff         : DISABLED (None)
Deployments with desktops: 217
Empty deployments        : 84  (cron's eq_join skips these)

⚠ No cutoff configured — the recycler is a no-op by design.
```

or:

```
Effective cutoff         : 6 months
Violations (>6mo idle, ≥1 ready storage): 142  (1834.50 GB)

⚠ Recycler is NOT removing these deployments — see
  /logs/analyze/202604301730/deployment_recycler_violations.tsv
```

### `sizes`, `integrity`, `by-role`, `chains` (read-only mode)

See `storage <cmd> --help`. None of these write to disk or API as long as
the destructive flags below (`--flatten-singles`, `--flatten-deep`) are not used.

---

## Destructive commands

⚠ The commands below modify production state — files on disk and/or rows in
the API. Always run a `cleanup` first and review the relevant TSVs before
proceeding. Where possible, use `--dry-run`-equivalent options first.

### `cleanup --move`

Moves files listed in `bad_*.txt` into `/isard/volatile/to_delete/`. Does
**not** `rm`. Templates are skipped unless `--include-templates` is set.

```bash
storage cleanup --move                       # move bad_* (skip templates)
storage cleanup --move --interactive         # walk through buckets safest first
storage cleanup --move --include-templates   # also move template files
```

### `repair-chains --apply`

Runs `qemu-img rebase` on broken backing chains. Read-only without `--apply`.

```bash
storage repair-chains              # diagnose only
storage repair-chains --apply      # actually rebase
```

### `verify --fix`

DB-vs-disk consistency check. With `--fix` it updates DB `path` fields for
mismatched files and triggers `find` tasks for missing/ghost rows.

### `recover --apply`

Recreates missing incremental disks to recover failed desktops.

### `chains --flatten-singles | --flatten-deep N`

Disconnects single-dependent intermediate templates (`--flatten-singles`) or
flattens leaves deeper than N (`--flatten-deep N`).

### `full-cleanup`

One-shot maintenance: `verify --fix` + `repair-chains --apply` + move unusable
files. Optionally `--sparsify` and `--compress`. **Highest blast radius** —
read its `--help` and the produced report carefully before re-running.

Use `--dry-run` to preview the entire pipeline without touching anything:

```bash
storage full-cleanup --dry-run
```

The dry-run produces the same `bad_*`/`ok_*` file lists as a real run,
plus `dry_run_actions.jsonl` (one JSON object per planned action: rebase
of broken chain, sparsify+compress of healthy file, move of unusable
file) and `would_move.txt` listing every file that would have been moved
to `/isard/volatile/to_delete/`. Review those before re-running without
`--dry-run`.

### `db-cleanup`

Detect malformed `storage` rows in the database. Three classes are
scanned, each driven by a real-world bug pattern observed in production:

- **Zombie rows** — only `id`, no other fields. The residue of
  `Storage(<unknown_id>)` calls hitting the insert-on-construct bug in
  `RethinkBase.__init__` (see upstream branch `fix/storage-stub-rows-rethinkbase`).
- **Path-shaped ids** — `id` is a `/isard/...qcow2` string instead of a
  UUID. Same root cause, but the unknown id was a parent path.
- **Path-shaped `parent` fields** — row is otherwise fine but its
  `parent` field is a path string. The chain still works on disk, but
  any DB-level join on `parent` fails. **Reported only**, never
  auto-rewritten.

Default mode is read-only: writes three JSONL reports under the
timestamped output dir:

- `db_cleanup_pending.jsonl` — rows safe to delete (not referenced by
  any domain, recycle_bin entry, or `storage.parent`).
- `db_cleanup_kept_referenced.jsonl` — rows still referenced; investigate
  before any action.
- `db_cleanup_path_parents_review.jsonl` — rows whose `parent` is a path.

To actually delete the verified-safe rows:

```bash
storage db-cleanup --apply           # prompts y/N
storage db-cleanup --apply --yes     # CI/automation, skip the prompt
```

Each deletion re-runs the reference check immediately before the delete
and writes an audit line to `db_cleanup_deleted.jsonl`.

### `sparsify`

Thin wrapper around the standalone `/utils/sparsify` script. Forwards all
flags verbatim:

```bash
storage sparsify --help                  # forwarded to /utils/sparsify -h
storage sparsify /isard/groups -r        # sparsify recursively
```

The script creates `<file>.sparsify-backup` before each operation and
arms an EXIT/INT/TERM trap that, on unexpected termination, validates
the destination via `qemu-img check` and either removes the backup
(dest valid) or restores it (dest broken). This prevents the
`*.sparsify-backup` orphans that previously showed up in
`storage cleanup`'s `bad_non_qcow2` list when a sparsify run was killed.

---

## End-to-end analysis workflow

The four read-only commands chain into a complete diagnostic. None of them
delete anything; they just produce TSVs you can review and act on.

```bash
# 1. Filesystem + API analysis (produces report dir + .meta.tsv sidecars).
storage cleanup
RUN=$(ls -1dt /logs/analyze/2* | head -1)
echo "Working with $RUN"

# 2. Age distribution.
storage age-report "$RUN" --bucket month
storage age-report "$RUN" --bucket year   --filter ok_no_derivatives
storage age-report "$RUN" --bucket month  --filter bad_deletable_orphans --per-file

# 3. Deployment ownership of each cleanup bucket.
storage deployments "$RUN"
storage deployments "$RUN" --per-file --filter bad_deletable_orphans

# 4. Audit the auto-recycler.
storage recycler-audit --output-dir "$RUN"
storage recycler-audit --output-dir "$RUN" --cutoff-months 6   # what-if

# 5. Cross-reference: orphan files belonging to stale deployments.
cut -f1 "$RUN/deployment_recycler_violations.tsv" | tail -n +2 > /tmp/stale_deps.txt
grep -F -f /tmp/stale_deps.txt "$RUN/bad_deletable_orphans.deployments.tsv" | wc -l
```

## Viewing TSV output

```bash
column -t -s $'\t' "$RUN/deployment_recycler_violations.tsv" | less -S
awk -F'\t' '{print $4, $1}' "$RUN/deployment_recycler_audit.tsv" | sort -n | tail -20
sort -t$'\t' -k4 -n "$RUN/deployment_recycler_audit.tsv" | tail -20    # most idle
```

## Output layout reference

```
/logs/analyze/<YYYYMMDDHHMM>/
├── README.md                                  # cleanup summary
├── bad_broken_chain.txt
├── bad_broken_chain.meta.tsv                  # path  size_bytes  mtime_iso
├── bad_broken_chain.deployments.tsv           # added by `storage deployments`
├── bad_deletable_orphans.txt
├── bad_deletable_orphans.meta.tsv
├── bad_deletable_orphans.deployments.tsv
├── bad_non_qcow2.{txt,meta.tsv,deployments.tsv}
├── bad_orphan_medias.{txt,meta.tsv,deployments.tsv}
├── bad_db_storage_entries.jsonl               # DB review, do NOT delete files
├── bad_db_media_entries.jsonl
├── ok_*.{txt,meta.tsv}                        # informative
├── ok_no_derivatives.deployments.tsv          # added by `storage deployments`
├── volatile_storage.{txt,meta.tsv}
├── deployment_recycler_audit.tsv              # added by `storage recycler-audit`
├── deployment_recycler_violations.tsv
└── deployment_recycler_empty.tsv
```

## Why the recycler audit matters

The cron `system.send_unused_items_to_recycle_bin` (daily 23:30) is the only
mechanism that deletes unused deployments. Known limitations baked into its
current implementation:

1. Default `unused_item_timeout.send_unused_deployments_to_recycle_bin.cutoff_time`
   is `None` → the cron is a no-op until an admin sets a value.
2. Value is interpreted as **months** (`timedelta(days=cutoff_time * 30)`).
   Easy to misconfigure thinking it's days.
3. The eq_join in `get_unused_deployments()` silently drops deployments with
   zero tagged desktops — those live forever (`deployment_recycler_empty.tsv`).
4. A single recently-launched desktop shields the **entire** deployment from
   recycling (`max(accessed)` reducer). There is no per-desktop pruning.
5. Only desktop launches refresh `domains.accessed`. Browsing the deployment
   in the UI without launching a desktop is invisible to the recycler.

`recycler-audit` exposes (1)–(3) directly; (4)–(5) are inherent limitations
to keep in mind when interpreting violations.
