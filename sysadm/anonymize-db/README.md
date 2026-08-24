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
| `config` | the three `auth.{ldap,saml,google}.*_config` blocks (see below), top-level `smtp.*` including the pre-v175 `server`/`sender_address`/`sender_name` names (and SMTP disabled), `resources.url` + the `code` / `private_code` repository tokens, `engine.api.token`, server wireguard, grafana hostname + url, maintenance text, and the operator-authored login copy — `login.info.title`, both notification banners (title / description / button text + url) and the per-provider descriptions, plus the top-level `notification_form`; `enabled`, `icon`, `locale` and the `extra_styles` CSS stay |
| `categories` | name, description, custom_url_name, uid, branding domain, `email_domain_restriction.allowed`, **its own copy of the `authentication.{ldap,saml,google}.*_config` blocks** (a category with `config_source: "custom"` carries the customer's directory host, service-account DN and IdP endpoints), its own `login_notification` banners (the per-category twin of `config.login`) and `bastion_domain` |
| **all tables** | defensive recursive sweep clears any unhandled key matching `[<word>_]password\|passwd\|passphrase\|secret\|client_secret\|api_key\|api-key\|private_key\|private_code\|access_key\|secret_key\|bearer\|token\|auth_token\|access_token`. The optional `<word>_` / `<word>-` prefix is what makes it a net rather than a list — a fully anchored alternation misses every composite name a new field can be given (`smtp_password`, `bind_password`, `refresh_token`, `api_token`) |

### Authentication providers

The `{ldap,saml,google}_config` blocks appear **twice** — globally under `config.auth.<provider>`
and per category under `categories[].authentication.<provider>` — and one routine
(`Scrubber._scrub_provider_config`) handles both, walking the whole document so a future nesting
change cannot silently drop coverage. Field names come from `authentication/model/config.go`
(`LDAPConfig`, `SAMLConfig`, `GoogleConfig`), which is the authoritative shape; the pydantic
schemas and the frontend name some of them differently.

Replaced: `name`, LDAP `host` / `bind_dn` / `base_search` / `password` / `filter` /
`role_list_search_base` / `role_list_filter`, SAML `metadata_url` / `metadata_file` / `entity_id` /
`key_file` / `cert_file` / `logout_redirect_url`, Google `client_id` / `client_secret`, every
`role_*_ids` list (real AD group DNs) and every `regex_*` (reset to `.*` — the one place org
patterns get pasted).

Kept: booleans, ports, enums, the `field_*` directory-attribute mappings and `role_default`. Those
are schema shape rather than identity, so a dev restore still exercises the same code paths.

Primary keys and FK relationships are preserved. Any value that is replaced and also
appears in another table (user email / name / username / uid, category & group uid,
media path) is registered in a remap and rewritten **consistently** across every table
by a final cross-table pass.

Every field the scrubber touches falls into exactly one bucket:

| Bucket | Definition | Treatment |
| --- | --- | --- |
| Identity | Identifies a person or the customer organisation | Stable pseudonym, propagated to every denormalized copy |
| Dimension / FK | An id or grouping key; identifies nobody on its own | Preserved verbatim. A stable alias (`hyp-01`, …) only where the literal value names real infrastructure |
| Human free text | `description`, titles, admin notes | Blanked |

Blanking a field that is a foreign key or a grouping dimension is a bug, not a
precaution: it breaks the guarantee above. Denormalized display names are
rebuilt from their foreign key (`desktop-<id8>`, `deployment-<id8>`,
`user-<id8>`, `group-<id12>`, `category-<id>`) rather than emptied, so
grouping still works on an anonymized dump.

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

### Carrying tables empty (`--empty-tables`)

A third, blunter option: carry a table with **no rows at all**. Its rows are dropped whole and never
scrubbed, while the table itself is preserved — the `.info` beside it holds the primary key and every
secondary index, so a restore rebuilds it complete and it simply has nothing in it. Same shape the
drop-scrubbers already produce for `hypervisors`, `gpus` and friends.

```
anonymize-db --input prod.tar.gz --empty-tables                  # the default set
anonymize-db --input prod.tar.gz --empty-tables logs_users,bookings
```

With no value the flag empties `logs_desktops`, `logs_users` and `usage_consumption`. On a
production-shaped dump (4.79 GB of JSON across 59 tables) those three are **80.6% of the bytes** —
45.9%, 27.1% and 7.6% — and none of them is needed to exercise the product. Naming a table that is
not in the dump logs a warning rather than failing.

The rest of the `usage_*` family is deliberately **not** in the default set: `usage_credit` and its
siblings are the feature's configuration rather than its time series, and they cost kilobytes.

The saving is not only bytes. An emptied table is skipped by the scrub, by the prune and by the
cross-table rewrite pass — and that last one is where the time goes: on the dump above it took 17
minutes to make 15,224 replacements, every one of them in `users` and `domains`, after walking 5.6
million log and usage rows for nothing.

**This empties the admin users/desktops logs and the usage history**, so don't use it when those are
what you are testing. Between "everything" and "empty" sits `--cap-history-days N`.

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
