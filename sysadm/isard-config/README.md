# isard-config

A standalone, **stdlib-only** Python 3 CLI to read and change the runtime
"neteja/retenció" admin settings of **any** IsardVDI installation over its
public REST API — as an admin. Meant as an ops tool a sysadmin runs from their
laptop against a production install after an upgrade, to verify/adjust settings
that live in the RethinkDB `config`/`scheduler` tables (not in `isardvdi.cfg`).

No third-party dependencies (`urllib`, `argparse`, `getpass`, `json`, `ssl`).

## Install / run

```bash
python3 isard_config.py --url https://<domain> [--category default] [--insecure]
```

Username is prompted (or `--user`); the password is **always** prompted via
`getpass` — never passed on the command line.

## What it can read/set

Run `--list-keys` for the authoritative list. Covered setting groups:

| Group | GET | SET keys |
|-------|-----|----------|
| Recycle bin system cutoff (hours) | ✓ | `recycle_bin_cutoff` |
| Recycle bin old-entries retention | ✓ | *(read-only)* |
| Logs desktops retention | ✓ | `logs_desktops.max_time` (hours, ≥24), `logs_desktops.action` (`delete`/`none`) |
| Logs users retention | ✓ | `logs_users.max_time`, `logs_users.action` |
| Redis old tasks | ✓ | `old_tasks.older_than` (seconds, ≥86400), `old_tasks.enabled` (bool) |
| Usage/consumption retention (months) | ✓ | `usage.daily_months` (1–120), `usage.weekly_months` (2–120), `usage.total_months` (1–240, nullable) |
| Scheduler jobs | ✓ (`--list-schedulers`) | read-only |

Every endpoint is one of the apiv4 admin routes in the committed OpenAPI spec
(`pkg/oas/apiv4/apiv4.json`). The `usage.*` bounds above come straight from the
spec's `UsageRetentionConfig`.

## Examples

```bash
# GET everything (grouped, human readable), or --json
isard_config.py --url https://vdi.example.org
isard_config.py --url https://vdi.example.org --json

# List scheduler jobs (read-only)
isard_config.py --url https://vdi.example.org --list-schedulers

# SET (repeatable). Shows old->new, asks to confirm (unless --yes), applies,
# then re-reads to confirm it stuck.
isard_config.py --url https://vdi.example.org --set recycle_bin_cutoff=720
isard_config.py --url https://vdi.example.org \
    --set logs_desktops.max_time=365 --set logs_desktops.action=delete
isard_config.py --url https://vdi.example.org \
    --set old_tasks.older_than=604800 --set old_tasks.enabled=true
```

## How SET verification works (important)

Several apiv4 config **getters are server-side `@cached`** (TTLs of 5–60 s) and
the corresponding **setters do not invalidate that cache**. So an immediate
re-read after a write can return the *old* value even though the write
succeeded. This tool therefore treats the write `PUT` returning `2xx` as the
authoritative "applied" signal, and then **polls** the re-read (default up to
20 s, tune with `--verify-timeout`) until it reflects the new value:

- `CONFIRMED` — re-read now returns the new value.
- `UNCONFIRMED` — the `PUT` was accepted (written) but the cache had not
  refreshed within the timeout. This is **not** a write failure; raise
  `--verify-timeout` or re-GET a moment later.

## Auth & admin gate

1. `GET /api/v4/items/categories` to resolve `--category`.
2. `POST /authentication/login?provider=form&category_id=<id>` with a
   **multipart** body (`username`, `password`) → JWT in the `Authorization`
   response header.
3. The tool decodes the JWT payload and **refuses** (exit code 3) unless
   `data.role_id == "admin"`. The apiv4 admin routes enforce this server-side
   too (403 without an admin token).

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success (GET, or SET fully CONFIRMED) |
| 1 | Login failed / API unreachable / SET aborted at confirmation |
| 2 | SET applied but at least one key left UNCONFIRMED within the timeout |
| 3 | Logged-in user is not an admin |

## Tests

Pure units (arg parsing, key map, coercion, request building, JWT decode, URL
building, and the SET verification polling loop) are covered with stdlib
`unittest`:

```bash
python3 -m unittest -v test_isard_config
```

Behaviour against the API was verified live against a running stack.
