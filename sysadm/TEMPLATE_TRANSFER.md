# Template Transfer

`sysadm/template_transfer.py` ports an IsardVDI **template** (its flattened qcow2
disk, its `domains` + `storage` documents, and any user card) from one installation
to another over SSH.

It is the automated successor to the manual "move a template between installs" recipe
and the old `dump.py`. It is safe by design: the **source is never modified**, and it
**fails closed** — a list of pre-flight checks must pass before anything is written on
either side.

## How it works

For each template, on the **source host**:

1. Read the `domains` + `storage` docs from RethinkDB (through `isard-storage`).
2. Run all pre-flight gates (see below). Abort the template on any blocking failure.
3. Flatten the disk into a **copy** — `qemu-img convert -U` to a new file under
   `/opt/isard/templates/dump/converting/` (the original disk is never touched), then
   `qemu-img check` it. Optionally `virt-sparsify` / compress.
4. `rsync` the copy (and the user card, if any) to the destination.
5. On the **destination** (through its `isard-storage`): re-check the landed disk,
   remap ownership, normalise the docs, and insert them — rolling back on any error.

### Everything DB/qemu runs inside `isard-storage`

All RethinkDB and qemu-img work runs via `docker exec … isard-storage` on the
respective host (the remote side over SSH). The connection uses
`RETHINKDB_HOST/PORT/DB` from `isardvdi.cfg` (sourced from
`/usr/local/etc/environment`) or the defaults `isard-db:28015/isard`. **The host
needs only `docker` and `ssh`** — no python rethinkdb driver, no DB IP guessing.

Only `ssh`/`rsync` run on the host itself (they need the host keys and read the
converted file via the `/opt/isard` bind mount).

## Requirements

- Run **on the source host**, as a user that can `docker exec isard-storage` and `ssh`
  to the destination (key-based auth).
- The **destination** must have a running `isard-storage` and a reachable `isard-db`.
- `--remote-user` must be an existing user id on the destination (it becomes the owner).

## Safety model (fail-closed gates)

Every gate runs **before any mutation**, and `--dry-run` runs all of them and changes
nothing. Blocking failures abort that template; nothing is partially applied.

**Source stays untouched**
- The disk is flattened into a *copy*; the source disk and its derived desktops are
  never written, and the source DB is read-only. The source disk size+mtime is checked
  before/after (`--verify-source-hash` adds a sha256 check).
- Aborts if the source disk is missing or its storage is not `ready` (mid-operation).

**Destination is never clobbered**
- Aborts if the domain id, storage id, or user-card file already exists.
- Aborts if `--remote-user` does not exist, or if there is not enough free space
  (checked on both sides).
- The landed disk is `qemu-img check`-ed **before** it is registered.
- Insert is storage→domain with rollback of the storage row if the domain insert fails.

**Re-runs are safe**
- A completed transfer re-run aborts cleanly on the id-exists gate (no duplicates).
- An interrupted transfer **resumes**: rsync continues the partial file, and a valid
  already-converted copy is reused instead of being regenerated.

## Domain reimport: schema & missing resources

The `domains` document is portable on current IsardVDI: the disk is referenced by
`create_dict.hardware.disks[0].storage_id`, and the stored `xml` is a static base —
the engine regenerates the real XML from `create_dict` at boot, so host-specific paths
are recomputed on the destination.

On import the restore step **remaps ownership** (`user`/`username`/`category`/`group`
→ `--remote-user`; `storage.user_id`) and resets deployment/host-specific fields to
safe defaults (`status=Stopped`; `storage` flattened to `parent=None`/`status=ready`/
read-only; `tag*`/`booking_id` cleared; `parents=[]`; and `hypervisors_pools`/
`forced_hyp`/`favourite_hyp` reset to defaults unless `--keep-hyp-pools`).

**Missing referenced resources never fail the import.** If a referenced id does not
exist on the destination it is **pruned (or replaced by the IsardVDI default)** with a
warning, so the template still imports and works:

| Reference            | If missing on destination                                   |
|----------------------|-------------------------------------------------------------|
| `interfaces`         | dropped (no NIC); `--reset-network` forces the default NIC  |
| `graphics`/`videos`  | dropped; falls back to stock `default` if it would be empty |
| `media` (ISOs/flop.) | dropped (boots without it); `--clear-media` drops all       |
| `reservables.vgpus`  | dropped; `None` if it would be empty; `--clear-vgpu` clears |
| `hypervisors_pools`  | reset to `["default"]` (kept+pruned with `--keep-hyp-pools`)|

`--dry-run` reports exactly what would be pruned, per template.

## Speed & resume

qcow2 is already compressed, so the defaults avoid wasting CPU on it. Resumability is
always on (`rsync --partial --append-verify`, whole-file).

- `--fast` — recommended on a LAN: no compression + whole-file + SSH multiplexing +
  `aes128-gcm@openssh.com`. Fully encrypted **and** resumable; near wire-speed on AES-NI.
- `--ssh-cipher CIPHER` — override the cipher (e.g. `chacha20-poly1305@openssh.com`).
- `--bwlimit KB/s` — cap bandwidth (unset = max).
- `--sparsify` / `--compress` — shrink the disk before sending (good on slow WANs;
  `--compress` is mutually exclusive with `--fast`).
- `--insecure-net` — **plaintext** disk transport over `nc` for trusted high-throughput
  links (SSH is still used for control). Offset-resumable, sha256-verified; needs `nc`
  on both ends and an open `--insecure-net-port` (default 9920). Forces `--workers 1`.

## Usage

```bash
# Dry run — show every gate and what would be pruned, change nothing
sysadm/template_transfer.py transfer-templates \
    --domains UUID1,UUID2 --remote-host root@dest-host --remote-user <dest-user-id> --dry-run

# Transfer (LAN, fast + resumable)
sysadm/template_transfer.py transfer-templates \
    --domains UUID1,UUID2 --remote-host root@dest-host --remote-user <dest-user-id> --fast

# Many templates from a file, 4 workers, keep the converted copies
sysadm/template_transfer.py transfer-templates \
    --domains-file templates.txt --remote-host root@host --remote-user U --workers 4 --keep-converted

# Slow WAN — shrink before sending
sysadm/template_transfer.py transfer-templates \
    --domains UUID1 --remote-host root@host --remote-user U --sparsify --compress
```

Other options: `--remote-db-container NAME` (default `isard-storage`),
`--secure-ssh` (verify host keys instead of disabling), `--verify-source-hash`, and
the normalisation flags `--reset-network` / `--clear-vgpu` / `--clear-media` /
`--keep-hyp-pools`.

## Limitations

- One disk per template (`disks[0]`); multi-disk templates are skipped with an error.
- Assumes source and destination share the storage-pool layout (the standard default
  pool, `directory_path = /isard/templates`). Non-default per-category pools are not
  remapped.
- `--insecure-net` depends on `nc` and an open port between the hosts (trusted LAN only).

## Legacy commands

`dump <domain-id>` and `restore <user-id>` are the older **local** dump/restore
(no SSH); kept only for backward compatibility — prefer `transfer-templates`. They
require the python `rethinkdb` module on the host.
