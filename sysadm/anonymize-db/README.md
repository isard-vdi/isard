# anonymize-db

Anonymize an IsardVDI `rethinkdb-dump` archive so it can be safely used in development.

## What it scrubs

| Table | What is replaced |
|------|------------------|
| `users` | password (bcrypt of `pirineus` for **all** users incl. the built-in `local-default-admin-admin`), email, name, username, uid, description, photo, api_key, password_history, password_reset_token, email_verification_token, accessed, vpn wireguard keypair, and the nested `user_storage.email` / `user_storage.displayname` |
| `domains` | name, description, username (derived from the `user` FK so it matches `users.username`), viewer (guest_ip/passwd/ticket/session_id), guest_properties.credentials, create_dict MAC addresses, libvirt XML (`<graphics passwd>`, `<channel><source path>`, `<log file>`, `<metadata>` notes), history_domain |
| catalog/resource tables (`user_networks`, `qos_net`, `qos_disk`, `graphics`, `videos`, `boots`, `disk_bus`, `virt_install`, `desktops_priority`, `bookings_priority`, `storage_pool`, `scheduler_jobs`, `roles`, `notification_tmpls`) | admin-/user-authored `name` (renamed) + `description` (blanked); primary-key `id` is preserved (referenced by id everywhere) |
| `hypervisors`, `vgpus`, `gpus`, `engine`, `secrets` | dropped entirely |
| `hypervisors_pools` | viewer.certificate / server-cert / host-subject |
| `targets` | ssh.authorized_keys |
| `remotevpn` | wireguard keypair |
| `media` | url-web, url-isard, path, path_downloaded |
| `vouchers` | code |
| `users_migrations` | token |
| `recycle_bin` | owner/agent names, nested name/email/ip/description fields |
| `logs_users`, `logs_desktops` | PII fields blanked (owner names, IPs, agents); **rows kept** for realistic dev volume |
| `config` | `auth.ldap` / `auth.saml` / `auth.google` credentials, top-level `smtp.*` (disabled), server wireguard, grafana hostname, resources url, maintenance text |
| **all tables** | defensive recursive sweep clears any unhandled key matching `password\|passwd\|secret\|client_secret\|api_key\|api-key\|private_key\|access_key\|secret_key\|bearer\|auth_token\|access_token` |

Primary keys and FK relationships are preserved. Any value that is replaced and also
appears in another table (user email / name / username / uid, category & group uid,
media path) is registered in a remap and rewritten **consistently** across every table
by a final cross-table pass.

## Install

```
cd sysadm/anonymize-db
uv venv && uv pip install -e .
```

`rethinkdb-dump` / `rethinkdb-restore` are picked up from `$PATH`. If absent, the tool falls back to `docker run --rm --network host` against the running `isard-db` container's image.

## Usage

Anonymize an existing dump:

```
anonymize-db --input prod.tar.gz --output anon.tar.gz
```

Dump a remote DB through an SSH jump host and anonymize (does **not** touch the local DB):

```
anonymize-db \
  --source-ssh user@jump.example.com:22 \
  --output /tmp/isard-anon.tar.gz
```

Same, then **explicitly** overwrite the local `isard-db` with the result:

```
anonymize-db \
  --source-ssh user@jump.example.com:22 \
  --output /tmp/isard-anon.tar.gz \
  --restore-local
```

Restore is off by default. Pass `--restore-local` (local `isard-db` at 127.0.0.1:28015), or `--restore-host HOST[:PORT]` / `--restore-ssh ...` for a different target. If the target DB already has data the tool prints a row-count summary and prompts for confirmation; `--yes` skips the prompt.

`--source-ssh-target` and `--restore-ssh-target` default to `172.31.255.13:28015` (the standard IsardVDI compose internal address). The tunnel binds a free localhost port and is torn down on exit.

SSH must work non-interactively (use `ssh-add` or `~/.ssh/config`).

## Trim / shrink (opt-in)

Two flags drop old rows to make the dump much smaller and faster (rows are
dropped **before** scrubbing, so they cost no work). Both are off by default;
pass the flag with no value for 30 days, or a day count:

- `--prune-deleted-days [N]` — drop entries in a *deleted* state older than N
  days: `recycle_bin` (by `accessed`), `storage` (status deleted/recycled/
  non_existing, by its last `status_logs` time), `media` (status deleted).
- `--cap-history-days [N]` — keep only the last N days of the time-series
  tables: `logs_desktops`, `logs_users`, `usage_consumption` (by their
  timestamp).

```
anonymize-db --input prod.tar.gz --prune-deleted-days 30 --cap-history-days 30
```

A summary of what was dropped is logged (e.g. `pruned 3296848 old/deleted rows:
…`). The whole pipeline streams one document at a time, so peak RAM stays
bounded (a few hundred MB) regardless of table size.

## Safety

The **dump / source** side (`--input`, `--source-host`, `--source-ssh`) is strictly
**read-only** — it runs `rethinkdb-dump` (an export) and writes only the local
anonymized tar.gz. It can never modify the source installation.

All writing happens in the **opt-in** `--restore-*` and `--with-fake-storage` flags,
which are guarded by two gates:

### Name-the-target confirmation (every destructive op)

Before any restore or fake-storage write, the tool **STOPS**, prints exactly *what*
will be overwritten on *which* installation (target DB + row counts, or the storage
container + file counts), and refuses to continue until you **assert the target by
name**:

- interactively: type the resolved installation name/domain at the prompt;
- non-interactively (CI / no TTY): pass `--confirm-target NAME`, which must match the
  host/install/domain the tool resolved (otherwise it aborts before writing anything).

`--yes` does **not** bypass this — a destructive write always requires naming the target.
For `--restore-ssh` the name is the Warpgate target (e.g. `prod-db-node`); for
`--restore-host` it is the host; for `--restore-local` it is `localhost`. This is the
guard against the `--restore-ssh` footgun where the tunnel makes a remote DB look like
loopback.

### USAGE=devel gate

Before any invasive action the tool also inspects every running `isard-*` container and reads the `USAGE` env var. It refuses to proceed if any container reports `USAGE=production` (or anything other than `devel`). If no container reports `USAGE` at all, the tool also refuses unless you pass `--i-know-what-im-doing`. `isard-db` itself doesn't carry `USAGE`; the marker comes from the Python services (`apiv4`, `engine`, `webapp`, `notifier`, `scheduler`). Note this gate inspects the **local** stack, not the restore target — the name-the-target confirmation above is what protects a remote/tunneled target.

## Fake storage / media (`--with-fake-storage`)

Pass `--with-fake-storage` after a restore flag (`--restore-local` etc.) to also materialise the qcow2 backing chain and zero-byte ISO placeholders the engine needs to actually start desktops, create templates, etc.

Prerequisites:
```
cd /opt/isard/src && docker compose up -d isard-storage
```

The tool then runs `qemu-img create` inside `isard-storage` (override with `--storage-container NAME`) in topological order — roots (templates) first, then their children — so each child's `-b parent.qcow2` reference points at an already-materialised file. ISOs become zero-byte files at their `path_downloaded`. Existing files are kept; pass `--force-replace-files` to overwrite. After creation, a sample of leaves is verified with `qemu-img info --backing-chain` and the run fails loudly if any backing file is missing.

## Dev login after restore

All users (including the built-in `admin`) get the password **`pirineus`**.

`guest_properties.credentials` on every domain is rewritten to the IsardVDI demo defaults `isard` / `pirineus` so the dev viewers Just Work.

Every other password / secret / token field — anywhere in any table — is replaced with a fresh, unrelated `anon-<random>` token so structure and truthiness are preserved without leaking real values.
