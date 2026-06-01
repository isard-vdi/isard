# SPDX-License-Identifier: AGPL-3.0-or-later

"""HTTP API helpers for the storage CLI subcommands.

Ported from main 2026-06-01 to use the apiv4 generated client
(``isardvdi_apiv4_client``) instead of the apiv3 ``ApiRest`` removed
from ``isardvdi_common`` on apiv4-integration. The same auth +
client-builder pattern is used by ``move_disks`` and ``update_storages``
in this container.

Each helper returns plain dicts (via generated-model ``.to_dict()``) so
existing CLI consumers' dict-access patterns (``s["id"]``,
``s.get("accessed")``) keep working without rewrites.
"""

import time

import httpx
from isardvdi_apiv4_client.api.role_admin import admin_storage_by_role
from isardvdi_apiv4_client.api.role_admin import (
    disconnect_storage as disconnect_storage_op,
)
from isardvdi_apiv4_client.api.role_admin import find_storage as find_storage_op
from isardvdi_apiv4_client.api.role_admin import set_storage_path as set_storage_path_op
from isardvdi_apiv4_client.api.role_manager import (
    admin_media_list,
    admin_storage_by_status,
    admin_storage_info,
    admin_storage_list,
    admin_table_list,
)
from isardvdi_apiv4_client.api.role_user import get_task as get_task_op
from isardvdi_apiv4_client.models import StoragePathRequest, TableListRequest
from isardvdi_apiv4_client_auth import build_client, raise_for_status

from .formatting import log

_SERVICE = "isard-storage"


def _client(timeout=120.0):
    """Return an ``AuthenticatedClient`` for apiv4 with a fixed timeout.

    Used inside ``with _client() as client:`` blocks so the underlying
    httpx connection is closed deterministically.
    """
    return build_client(_SERVICE).with_timeout(httpx.Timeout(timeout))


def _as_dict(obj):
    """Convert a generated-client model (or list of them) to plain dict(s).

    Generated models are ``attrs`` classes with ``to_dict()`` that
    flattens ``additional_properties`` back to their server-side keys
    (preserving hyphens, etc. — e.g. ``qemu-img-info``,
    ``directory_path``).
    """
    if obj is None:
        return None
    if isinstance(obj, list):
        return [_as_dict(i) for i in obj]
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return obj


def _fetch_table(table, *, pluck=None, timeout=120.0):
    """Generic POST /admin/items/table/{table} reader.

    Used by the ``fetch_*`` helpers below that previously called
    apiv3's ``POST /admin/table/{table}`` with ``{"pluck": [...]}``.
    """
    body = TableListRequest()
    if pluck is not None:
        body.pluck = pluck
    with _client(timeout=timeout) as client:
        resp = admin_table_list.sync_detailed(table=table, client=client, body=body)
        raise_for_status(resp)
        rows = _as_dict(resp.parsed) or []
    if isinstance(rows, dict):
        rows = [rows]
    return rows


def fetch_storages(status_filter=None):
    """Fetch all storages from API.

    Returns list of dicts with at least: id, type, status, directory_path, path,
    qemu-img-info (with actual-size, virtual-size), domains (count).

    The 'path' field is constructed as directory_path/id.type.
    """
    log("Fetching storage records from API (GET /admin/items/storage)...")
    start = time.time()
    try:
        with _client() as client:
            if status_filter:
                resp = admin_storage_by_status.sync_detailed(
                    status=status_filter, client=client
                )
            else:
                resp = admin_storage_list.sync_detailed(client=client)
            raise_for_status(resp)
            storages = _as_dict(resp.parsed) or []
    except Exception as e:
        log(f"WARNING: could not fetch storage from API: {e}")
        return None

    # Records missing directory_path / id / type can't have a file on disk.
    # They're DB-side issues (stale rows, partial uploads, schema drift).
    # Don't crash the run — separate them out so the caller can report them.
    valid = []
    bad = []
    for s in storages:
        missing = [f for f in ("id", "type", "directory_path") if not s.get(f)]
        if missing:
            entry = dict(s)
            entry["_missing_fields"] = missing
            bad.append(entry)
            continue
        s["path"] = f"{s['directory_path']}/{s['id']}.{s['type']}"
        valid.append(s)

    fetch_storages.last_bad_records = bad

    elapsed = time.time() - start
    if bad:
        log(
            f"Fetched {len(valid)} storage records ({len(bad)} bad records"
            f" with missing fields, see bad_db_storage_entries.jsonl) in"
            f" {elapsed:.1f}s"
        )
    else:
        log(f"Fetched {len(valid)} storage records in {elapsed:.1f}s")
    return valid


fetch_storages.last_bad_records = []


def fetch_storage_lookup():
    """Fetch storages and return a lookup dict: storage_id -> {status, has_domains, path}.

    This is the format needed by the sizes subcommand for classification.
    """
    storages = fetch_storages()
    if storages is None:
        return None

    lookup = {}
    for s in storages:
        lookup[s["id"]] = {
            "status": s.get("status", "unknown"),
            "has_domains": s.get("domains", 0) > 0,
            "path": s["path"],
        }
    return lookup


def fetch_storage_paths():
    """Fetch all non-deleted storage paths from API.

    Returns list of path strings (directory_path/id.type).
    Replaces the old direct RethinkDB get_db_storages() function.
    """
    storages = fetch_storages()
    if storages is None:
        return []
    return [s["path"] for s in storages]


def fetch_storages_with_size():
    """Fetch storages with qemu-img-info.actual-size for size comparison.

    Returns list of dicts with: id, path, status, db_actual_size.
    Replaces the old direct RethinkDB get_db_storages_with_size() function.
    """
    storages = fetch_storages()
    if storages is None:
        return []

    result = []
    for s in storages:
        qemu_info = s.get("qemu-img-info", {}) or {}
        result.append(
            {
                "id": s["id"],
                "path": s["path"],
                "status": s.get("status", "unknown"),
                "db_actual_size": qemu_info.get("actual-size", 0) or 0,
            }
        )
    return result


def fetch_domains_accessed():
    """Fetch domain accessed times from API.

    Returns dict mapping storage_id -> domain_accessed (ISO string).
    """
    log("Fetching domain accessed times from API (POST /admin/items/table/domains)...")
    start = time.time()
    try:
        domains = _fetch_table(
            "domains",
            pluck=[
                "id",
                "accessed",
                {"create_dict": {"hardware": {"disks": True}}},
            ],
        )
    except Exception as e:
        log(f"WARNING: could not fetch domains from API: {e}")
        return {}

    elapsed = time.time() - start
    lookup = {}
    for d in domains:
        accessed = d.get("accessed")
        disks = d.get("create_dict", {}).get("hardware", {}).get("disks", [])
        for disk in disks:
            sid = disk.get("storage_id")
            if not sid:
                continue
            if sid not in lookup or (accessed and accessed > lookup.get(sid, "")):
                lookup[sid] = accessed

    log(
        f"Fetched {len(domains)} domains, mapped {len(lookup)} storage->accessed"
        f" entries in {elapsed:.1f}s"
    )
    return lookup


def fetch_users_roles():
    """Fetch user → role mapping from API (POST /admin/items/table/users).

    Returns {user_id: role}. Roles in IsardVDI: admin, manager, advanced, user.
    """
    log("Fetching user roles from API (POST /admin/items/table/users)...")
    try:
        users = _fetch_table("users", pluck=["id", "role"], timeout=60.0)
    except Exception as e:
        log(f"WARNING: could not fetch users: {e}")
        return {}
    return {u["id"]: u.get("role") for u in users if u.get("id")}


def fetch_domain_deployments():
    """Fetch domain → deployment mapping from API.

    A desktop "belongs to a deployment" when the domain row has a non-null
    `tag` field (the value is the deployment id; there is a `tag` secondary
    index on the `domains` table). Non-deployment desktops have tag=None.

    Returns a dict with:
      - domains:        {domain_id: {"name", "kind", "user", "tag",
                                     "storage_ids": [..]}}
      - storage_to_domain:    {storage_id: domain_id}
      - storage_to_deployment:{storage_id: deployment_id}
      - deployments:    {deployment_id: [domain_id, ...]}
    """
    log("Fetching domain deployments from API (POST /admin/items/table/domains)...")
    start = time.time()
    try:
        domains = _fetch_table(
            "domains",
            pluck=[
                "id",
                "name",
                "kind",
                "user",
                "tag",
                {"create_dict": {"hardware": {"disks": True}}},
            ],
        )
    except Exception as e:
        log(f"WARNING: could not fetch domains from API: {e}")
        return {
            "domains": {},
            "storage_to_domain": {},
            "storage_to_deployment": {},
            "deployments": {},
        }

    user_roles = fetch_users_roles()

    domains_idx = {}
    storage_to_domain = {}
    storage_to_deployment = {}
    storage_to_role = {}
    deployments = {}
    for d in domains:
        did = d.get("id")
        if not did:
            continue
        tag = d.get("tag") or None
        uid = d.get("user")
        role = user_roles.get(uid)
        disks = d.get("create_dict", {}).get("hardware", {}).get("disks", []) or []
        sids = [disk.get("storage_id") for disk in disks if disk.get("storage_id")]
        domains_idx[did] = {
            "name": d.get("name"),
            "kind": d.get("kind"),
            "user": uid,
            "role": role,
            "tag": tag,
            "storage_ids": sids,
        }
        for sid in sids:
            storage_to_domain[sid] = did
            if role:
                storage_to_role[sid] = role
            if tag:
                storage_to_deployment[sid] = tag
        if tag:
            deployments.setdefault(tag, []).append(did)

    elapsed = time.time() - start
    log(
        f"Fetched {len(domains)} domains; {len(deployments)} deployments;"
        f" {len(storage_to_deployment)} storage→deployment links in {elapsed:.1f}s"
    )
    return {
        "domains": domains_idx,
        "storage_to_domain": storage_to_domain,
        "storage_to_deployment": storage_to_deployment,
        "storage_to_role": storage_to_role,
        "deployments": deployments,
    }


def fetch_unused_item_timeouts():
    """Fetch the recycle-bin auto-delete cutoffs.

    Reads RethinkDB table `unused_item_timeout` (used by the daily
    `system.send_unused_items_to_recycle_bin` cron). Returns
    {op: cutoff_months_or_None}. Common keys:
        send_unused_desktops_to_recycle_bin
        send_unused_deployments_to_recycle_bin

    `cutoff_time` is interpreted by the recycler as months
    (timedelta(days=cutoff_time * 30)). A value of None disables the rule.
    """
    log(
        "Fetching unused_item_timeout config (POST /admin/items/table/unused_item_timeout)..."
    )
    try:
        rows = _fetch_table(
            "unused_item_timeout", pluck=["id", "cutoff_time"], timeout=30.0
        )
    except Exception as e:
        log(f"WARNING: could not fetch unused_item_timeout: {e}")
        return {}
    return {r.get("id"): r.get("cutoff_time") for r in rows if r.get("id")}


def fetch_storages_by_role(role):
    """Fetch storages for a given role.

    Returns list of storage dicts with path constructed.
    Filters to ready/recycled desktop storages.
    """
    with _client() as client:
        resp = admin_storage_by_role.sync_detailed(role=role, client=client)
        raise_for_status(resp)
        storages = _as_dict(resp.parsed) or []

    from datetime import datetime

    result = []
    for s in storages:
        if (
            "directory_path" not in s
            or s["status"] not in ("ready", "recycled")
            or s.get("kind") != ["desktop"]
        ):
            continue
        s["path"] = f"{s['directory_path']}/{s['id']}.{s['type']}"
        s["datetime"] = (
            datetime.fromtimestamp(s["latest_status_time"]).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            if "latest_status_time" in s
            else ""
        )
        result.append(s)
    return result


def fetch_medias():
    """Fetch all medias from API (GET /admin/items/media).

    Returns list of dicts with at least: id, status, path_downloaded,
    kind ('iso' | 'floppy' | 'qcow2' | …), domains (count of VMs that
    reference the media).

    Records missing path_downloaded can't be matched against the
    filesystem; they're split into fetch_medias.last_bad_records so
    the caller can report them without crashing the run.

    Returns None on API failure (caller should skip media classification
    and keep going — qcow2 cleanup is still valuable).
    """
    log("Fetching media records from API (GET /admin/items/media)...")
    start = time.time()
    try:
        with _client() as client:
            resp = admin_media_list.sync_detailed(client=client)
            raise_for_status(resp)
            medias = _as_dict(resp.parsed) or []
    except Exception as e:
        log(f"WARNING: could not fetch media from API: {e}")
        return None

    # Records whose status indicates the download never completed legitimately
    # never have path_downloaded set — the field is only written on success.
    # Treat them as informational, not bad.
    expected_no_path_statuses = {"deleted", "DownloadFailed", "Downloading"}

    valid = []
    bad = []
    info_never_downloaded = []
    for m in medias:
        if not m.get("path_downloaded"):
            entry = dict(m)
            if m.get("status") in expected_no_path_statuses:
                info_never_downloaded.append(entry)
            else:
                entry["_missing_fields"] = ["path_downloaded"]
                bad.append(entry)
            continue
        valid.append(m)

    fetch_medias.last_bad_records = bad
    fetch_medias.last_info_never_downloaded = info_never_downloaded

    elapsed = time.time() - start
    parts = [f"Fetched {len(valid)} media records"]
    extras = []
    if bad:
        extras.append(f"{len(bad)} bad records with missing path_downloaded")
    if info_never_downloaded:
        extras.append(
            f"{len(info_never_downloaded)} never-downloaded"
            f" (status in {sorted(expected_no_path_statuses)})"
        )
    if extras:
        parts.append("(" + ", ".join(extras) + ")")
    parts.append(f"in {elapsed:.1f}s")
    log(" ".join(parts))
    return valid


fetch_medias.last_bad_records = []
fetch_medias.last_info_never_downloaded = []


def trigger_find(storage_id):
    """Trigger a find task for a storage.

    GET /item/storage/{id}/find — returns a ``{task_id: ...}`` dict.
    """
    with _client(timeout=30.0) as client:
        resp = find_storage_op.sync_detailed(storage_id=storage_id, client=client)
        raise_for_status(resp)
        return _as_dict(resp.parsed)


def poll_task(task_id):
    """Get task status.

    GET /task/{task_id} — returns task dict with at least 'status' key.
    """
    with _client(timeout=30.0) as client:
        resp = get_task_op.sync_detailed(task_id=task_id, client=client)
        raise_for_status(resp)
        return _as_dict(resp.parsed)


def fetch_storage_by_id(storage_id):
    """Fetch a single storage record by ID.

    GET /admin/item/storage/info/{id} — returns storage dict.
    """
    with _client(timeout=30.0) as client:
        resp = admin_storage_info.sync_detailed(storage_id=storage_id, client=client)
        raise_for_status(resp)
        return _as_dict(resp.parsed)


def trigger_disconnect(storage_id, priority="low"):
    """Trigger disconnect (flatten) task for a storage.

    PUT /item/storage/{id}/disconnect/priority/{priority} — flattens
    the backing chain via qemu-img convert, making the file standalone.
    Returns a ``{task_id: ...}`` dict.
    """
    with _client(timeout=30.0) as client:
        resp = disconnect_storage_op.sync_detailed(
            storage_id=storage_id, priority=priority, client=client
        )
        raise_for_status(resp)
        return _as_dict(resp.parsed)


def update_storage_path(storage_id, new_path):
    """Update a storage's path in the DB and trigger validation.

    PUT /item/storage/{id}/path — sets directory_path, triggers find +
    pool update. Returns a ``{task_id: ...}`` dict.
    """
    body = StoragePathRequest(path=new_path)
    with _client(timeout=30.0) as client:
        resp = set_storage_path_op.sync_detailed(
            storage_id=storage_id, client=client, body=body
        )
        raise_for_status(resp)
        return _as_dict(resp.parsed)
