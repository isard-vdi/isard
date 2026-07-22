# anonymize-db — usage guide

`anonymize-db` produces a PII-free `rethinkdb-dump` tar.gz of an IsardVDI database. Optionally it restores the result into a local dev DB and materialises fake qcow2 backing chains + ISO placeholders so the engine can actually start desktops, create templates, and exercise every flow against production-shaped (but fully scrubbed) data.

This document is the operator manual. For the scrubbing rules table, see [README.md](README.md).

---

## Running the tool

The `anonymize-db` console script is installed into a local venv — it is not on your global `$PATH`. First-time setup (requires [`uv`](https://docs.astral.sh/uv/)):

```
cd sysadm/anonymize-db
./setup.sh
```

(equivalent to `uv venv && uv pip install -e .`).

Then invoke it one of two ways:

```
# from sysadm/anonymize-db, no activation needed:
uv run anonymize-db --source-ssh ops@jump:22 --output ~/dumps/today.tar.gz

# or activate the venv once per shell:
source .venv/bin/activate
anonymize-db --source-ssh ops@jump:22 --output ~/dumps/today.tar.gz
```

`rethinkdb-dump` / `rethinkdb-restore` are picked up from `$PATH`; if missing, the tool falls back to `docker run` against the running `isard-db` image.

The examples below all assume the script is on your `$PATH` (venv activated or `uv run` prefix).

---

## Pipeline

```
       ┌────────┐    ┌────────────┐    ┌─────────┐    ┌────────────────┐
 ----> │  DUMP  │ -> │  ANONYMIZE │ -> │ RESTORE │ -> │  FAKE STORAGE  │
       └────────┘    └────────────┘    └─────────┘    └────────────────┘
        always         always           opt-in          opt-in
       (read-only)    (local only)     (USAGE gate)    (USAGE gate)
```

Each stage logs `[N/total]` banners and per-table / per-row progress.

---

## Quick reference

| Goal | Command |
|------|---------|
| Anonymize an existing dump | `anonymize-db --input prod.tar.gz` |
| Pull production via SSH and just save a tar.gz | `anonymize-db --source-ssh user@jump:22` |
| Same, plus restore into local `isard-db` | `... --restore-local --auto-stop-start --yes` |
| Same, plus fake qcow2 chain + ISOs | `... --with-fake-storage` |
| Use a custom default-output dir | `... --output /tmp/anon.tar.gz` |

The anonymized tar.gz is **always** written. Default name: `./isard-anon-<UTC-timestamp>.tar.gz`.

---

## Source

Pick exactly one:

- `--input FILE` — operate on an existing `rethinkdb-dump` tar.gz.
- `--source-host HOST[:PORT]` — connect directly (default port 28015).
- `--source-ssh USER@JUMP[:PORT]` — open an `ssh -L` tunnel to a jump host, then dump through it. The remote DB endpoint reachable from the jump host is given by `--source-ssh-target HOST:PORT` (default `172.31.255.13:28015`, the IsardVDI compose bridge).

The tunnel binds a free localhost port and is torn down on exit (success or failure). SSH must work non-interactively (`ssh-add` your key, or use `~/.ssh/config`).

### Warpgate bastions

When the jump host is a [Warpgate](https://warpgate.null.page/) SSH bastion, the SSH username encodes both the Warpgate login and the downstream target as `login:target`. Quote the value so the shell doesn't choke on the colon:

```
anonymize-db \
  --source-ssh 'admin:prod-db-node@warpgate.example.com:2222' \
  --output ~/dumps/today.tar.gz
```

`--source-ssh-target` still defaults to `172.31.255.13:28015` (the compose-bridge address of `isard-db` as seen from the host that Warpgate forwarded you to).

---

## Restore (opt-in)

Restoring is **off by default**. Enable with one of:

- `--restore-local` — restore into the running local `isard-db` (uses `docker exec isard-db rethinkdb-restore` so no host network is needed).
- `--restore-host HOST[:PORT]` — restore into an arbitrary endpoint.
- `--restore-ssh USER@JUMP[:PORT]` — restore through an SSH tunnel; pair with `--restore-ssh-target`.

`--restore-db NAME` overrides the DB name (default `isard`).

Behaviour:

1. **DB drop** (default): the target DB is dropped before restore so stale rows from prior restores don't leak through. Pass `--keep-existing-db` to skip the drop.
2. **drop_db is hard-restricted** to local addresses (`127.x.x.x`, `localhost`, `172.31.x.x`). Anything else aborts with a clear error.
3. **Source-vs-target collision check**: if `--source-host == --restore-host`, drop_db refuses. SSH-tunneled sources never collide with local restore targets.
4. **Row-count warning**: before overwriting, the script prints the existing row counts of the target DB and prompts. `--yes` skips the prompt.

---

## Fake storage (opt-in)

`--with-fake-storage` materialises:

- one **fake qcow2** per `storage` row at `<directory_path>/<id>.qcow2`, with `-b parent` linkage. Created in **topological order**: roots (templates) first, then their children (desktops and sub-templates), so every child's `-b PARENT` points at an already-existing file.
- one **zero-byte placeholder** per `media` row of `kind: iso` at its `path_downloaded`.

Requires the storage container to be running:

```
cd /opt/isard/src && docker compose up -d isard-storage
```

`--storage-container NAME` overrides the container name (default `isard-storage`).
`--force-replace-files` overwrites existing files (default: skip).

After creation, a sample of leaves is verified with `qemu-img info --backing-chain`; any missing backing file fails the run.

---

## Safety gates

### USAGE=devel gate

Before any invasive op (restore or fake storage) the script inspects every running `isard-*` container and reads the `USAGE` env var (`isard-db` itself doesn't carry it; the marker comes from the Python services — `apiv4`, `engine`, `webapp`, `notifier`, `scheduler`).

| State | Behaviour |
|-------|-----------|
| any container reports `USAGE=production` (or anything ≠ `devel`) | hard refuse, no override possible |
| at least one reports `USAGE=devel`, none disagree | proceed |
| no container reports `USAGE` at all | refuse, can be bypassed with `--i-know-what-im-doing` |

To make the gate stop nagging on a real dev box, add a single line to `/opt/isard/src/isardvdi.cfg`:

```
USAGE=devel
```

### Dependent services warning

Services like `isard-api` and `isard-engine` connect to `isard-db` and will misbehave if the DB is swapped underneath them. The script:

- detects all running `isard-*` containers excluding `isard-db`, `isard-storage`, `isard-redis`, `isard-squid`,
- prints them with the exact `docker compose stop ...` / `start ...` commands,
- with `--auto-stop-start`: stops them before the restore and starts them again after, **even if the restore fails** (uses a `try/finally`),
- without `--auto-stop-start`: prompts for confirmation; `--yes` skips the prompt.

---

## Anonymization (always-on stage)

Always runs against the extracted dump. Highlights:

- `users.password` → bcrypt of `pirineus` for everyone (admin and regular users).
- `domains.guest_properties.credentials` → `{username: isard, password: pirineus}` (well-known IsardVDI demo creds, kept verbatim so dev viewers work).
- Every other `password` / `secret` / `*_token` / `private_key` / `access_key` / `secret_key` / `bearer` / `client_secret` / `api_key` field, anywhere in any table, → `anon-<random>`.
- WireGuard keypairs (users, hypervisors, remotevpn, vpn_hypers, vpn_users) → freshly generated X25519.
- libvirt XML: `<graphics passwd>`, `<channel><source path>`, `<log file>` stripped.
- `secrets`, `logs_users`, `logs_desktops` tables → emptied.
- `recycle_bin` free-text fields → blanked.
- `targets.ssh.authorized_keys` → emptied.
- MAC addresses → randomised in `02:xx:xx:xx:xx:xx` range.

Primary keys and FK relationships are preserved (so the resulting DB is referentially consistent).

---

## Examples

### Pull prod, anonymize, restore, fake storage, auto-stop dependent services

```
anonymize-db \
  --source-ssh user@jump.example.com:22 \
  --restore-local --with-fake-storage \
  --auto-stop-start --yes
```

Expected log structure:

```
[1/4] DUMP source DB
  ssh tunnel up → rethinkdb-dump (~20 s for ~1k rows)
[2/4] ANONYMIZE
  scrub [ 1/57] analytics       4 bytes
  scrub [ 2/57] authentication  ...
  ...
  anonymized tar.gz: ./isard-anon-<ts>.tar.gz (~260 KB)
[3/4] RESTORE into target DB
  stopping containers: isard-api, isard-engine
  dropping db 'isard' (clean restore)
  rethinkdb-restore --force
[4/4] FAKE STORAGE
  qcow2 [  1/117] ... [117/117]
  iso   [  1/22] ... [22/22]
  fake storage chain verified
  starting containers: isard-api, isard-engine
```

### Just keep an anonymized snapshot

```
anonymize-db --source-ssh ops@jump:22 --output ~/dumps/today.tar.gz
```

No DB is touched; safety gate doesn't fire.

### Re-import a saved anonymized tar.gz into local

```
anonymize-db --input ~/dumps/today.tar.gz --restore-local --auto-stop-start --yes
```

(Anonymization is re-run, so any new sensitive fields added to the tool catch up; the operation is idempotent.)

---

## Dev login after restore

| Account | Password |
|---------|----------|
| `admin` | `pirineus` |
| any other user | `pirineus` |
| `guest_properties` viewer creds on every domain | `isard` / `pirineus` |

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|------|
| `refusing to act: no running container reports USAGE=devel` | Add `USAGE=devel` to `/opt/isard/src/isardvdi.cfg`, or pass `--i-know-what-im-doing` after confirming this is a dev box. |
| `REFUSING: at least one container is NOT USAGE=devel` | Production / staging detected — never overridable. |
| `REFUSING to drop_db on '<host>:<port>': not a recognised local dev endpoint` | Restore target isn't loopback or 172.31.x. Use `--restore-local` or pass `--keep-existing-db`. |
| `--with-fake-storage requires the 'isard-storage' container to be running` | `cd /opt/isard/src && docker compose up -d isard-storage` |
| `cycle in storage parent FK` | A loop in `storage.parent` references — corrupt source data. Inspect manually. |
| Service still up after `--auto-stop-start` | Containers with `restart: always` may resurrect; the script's `start` step is idempotent but you may need `docker compose stop` to keep them down. |
