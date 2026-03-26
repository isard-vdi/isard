# SPDX-License-Identifier: AGPL-3.0-or-later

import time

from isardvdi_common.api_rest import ApiRest

from .formatting import log


def _get_api():
    return ApiRest()


def fetch_storages(status_filter=None):
    """Fetch all storages from API.

    Returns list of dicts with at least: id, type, status, directory_path, path,
    qemu-img-info (with actual-size, virtual-size), domains (count).

    The 'path' field is constructed as directory_path/id.type.
    """
    log("Fetching storage records from API (GET /admin/storage)...")
    api = _get_api()
    start = time.time()
    try:
        if status_filter:
            storages = api.get(f"/admin/storage?status={status_filter}", timeout=120)
        else:
            storages = api.get("/admin/storage", timeout=120)
    except Exception as e:
        log(f"WARNING: could not fetch storage from API: {e}")
        return None

    for s in storages:
        s["path"] = f"{s['directory_path']}/{s['id']}.{s['type']}"

    elapsed = time.time() - start
    log(f"Fetched {len(storages)} storage records in {elapsed:.1f}s")
    return storages


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
    log("Fetching domain accessed times from API (POST /admin/table/domains)...")
    api = _get_api()
    start = time.time()
    try:
        domains = api.post(
            "/admin/table/domains",
            data={
                "pluck": [
                    "id",
                    "accessed",
                    {"create_dict": {"hardware": {"disks": True}}},
                ]
            },
            timeout=120,
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


def fetch_storages_by_role(role):
    """Fetch storages for a given role.

    Returns list of storage dicts with path constructed.
    Filters to ready/recycled desktop storages.
    """
    api = _get_api()
    storages = api.get(f"/admin/storage/by-role/{role}", timeout=120)

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


def trigger_find(storage_id):
    """Trigger a find task for a storage.

    GET /storage/{id}/find — returns task_id string.
    """
    api = _get_api()
    return api.get(f"/storage/{storage_id}/find", timeout=30)


def poll_task(task_id):
    """Get task status.

    GET /task/{task_id} — returns task dict with at least 'status' key.
    """
    api = _get_api()
    return api.get(f"/task/{task_id}", timeout=30)


def fetch_storage_by_id(storage_id):
    """Fetch a single storage record by ID.

    GET /admin/storage/info/{id} — returns storage dict.
    """
    api = _get_api()
    return api.get(f"/admin/storage/info/{storage_id}", timeout=30)


def trigger_disconnect(storage_id, priority="low"):
    """Trigger disconnect (flatten) task for a storage.

    GET /storage/disconnect/{id}/priority/{priority} — flattens the backing
    chain via qemu-img convert, making the file standalone.
    Returns task_id string.
    """
    api = _get_api()
    return api.get(f"/storage/disconnect/{storage_id}/priority/{priority}", timeout=30)


def update_storage_path(storage_id, new_path):
    """Update a storage's path in the DB and trigger validation.

    PUT /storage/{id}/path — sets directory_path, triggers find + pool update.
    Returns task_id string.
    """
    api = _get_api()
    return api.put(f"/storage/{storage_id}/path", data={"path": new_path}, timeout=30)
