#!/usr/bin/env python3
import json
import os
import subprocess
import time

from rethinkdb import r

DB_HOST = os.environ.get("RETHINKDB_HOST", "172.31.255.13")
DB_PORT = int(os.environ.get("RETHINKDB_PORT", "28015"))
DB_NAME = os.environ.get("RETHINKDB_DB", "isard")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# The hypervisor registers with enabled=False on boot and only reaches
# status="Online", enabled=True once the engine orchestrator picks it up —
# roughly 90s after the stack starts. Booking/desktop specs that hit
# check_create_storage_pool_availability raise 428 no_storage_pool_available
# while get_cached_hypervisors_online() is still empty, so the whole suite
# must block here until a usable hypervisor exists. This mirrors the exact
# predicate that check passes on: Online + enabled + a non-empty storage pool.
HYPER_READY_TIMEOUT = int(os.environ.get("E2E_HYPER_READY_TIMEOUT", "240"))

# Tables that have no seed JSON but accumulate per-user state across runs and
# must be reset so dependent tests stay deterministic on re-runs against the
# same database. notifications_data records "user X has been notified of
# notification Y" — once present, the login-trigger fullpage notification
# stops firing, breaking the e2e login-fullpage test on every run after the
# first.
RESET_TABLES = ["notifications_data"]

# Tables that have seeded rows (kept) but may accumulate e2e-prefixed rows
# created by tests whose afterEach cleanup failed silently. A login-trigger
# fullpage notification left behind fires for every user on login — clean
# these up at the start of each run without touching the seeded records.
E2E_PREFIX_TABLES = ["notifications", "notification_tmpls"]

# Virtual size for a seeded disk with no ``virtual_size`` of its own. qcow2 is
# sparse, so the file this leaves on the volume is a few hundred KB.
SEED_DISK_SIZE = "1G"

# The one chain that stays fileless on purpose. A clone of a template whose
# backing file does not exist wedges in CreatingDisk, and that is the only
# state the engine accepts force_failed from, so e2e S4 (desktops.spec.js,
# "Retry on a Failed desktop") derives from this template to reach Failed
# deterministically. Its cross-category child is here too: the tests that use
# it (templates.spec.js S9) only read rows, and a standalone file under a row
# that declares a parent would contradict the chain it claims.
# Everything else gets a real file — claiming ``ready`` without one is what
# left the integration suite waiting for desktops that could never be created.
DISKLESS_STORAGE_IDS = {
    "storage-template-s9-seed",
    "storage-desktop-s9-cross-cat-01",
}


def materialize_media_files(media_rows):
    """Create placeholder files for media seeded as already Downloaded.

    The media seed only inserts the DB row — it marks ``empty-iso`` as
    ``Downloaded`` with a ``path_downloaded`` but never writes the file. Any
    desktop that attaches the media then fails to start with "Cannot access
    storage file ... No such file or directory". Touch an empty file so the
    media is genuinely usable. No-op when the media volume isn't mounted (the
    target dir is absent) — seed runs that don't drive real VM boots skip it.
    """
    for media in media_rows:
        if media.get("status") != "Downloaded":
            continue
        path = media.get("path_downloaded")
        if not path:
            continue
        media_dir = os.path.dirname(path)
        if not os.path.isdir(media_dir):
            print(
                f"Media dir '{media_dir}' not mounted; skipping file for '{media.get('id')}'"
            )
            continue
        if os.path.exists(path):
            continue
        try:
            with open(path, "w"):
                pass
            print(f"Created placeholder media file '{path}'")
        except OSError as e:
            print(f"Could not create media file '{path}': {e}")


def materialize_storage_files(storage_rows):
    """Create the qcow2 files behind storage rows seeded as ``ready``.

    Same gap as ``materialize_media_files``, one layer down: the seed
    inserts storage rows claiming ``ready`` but writes no disk. Deriving
    a desktop from a seeded template then fails in the storage worker
    with ``qemu-img: Could not open '<parent>': No such file or
    directory``, and the domain sits in ``CreatingDisk`` until the
    change-handler reconcile flips it to ``Failed`` — every template the
    seed ships is unusable. An empty file is not enough here: qemu-img
    must be able to open the parent as qcow2, so the file is created
    with qemu-img itself. No-op when the volume isn't mounted or
    qemu-img isn't installed.
    """

    def _path(storage):
        return os.path.join(
            storage["directory_path"], f"{storage['id']}.{storage.get('type', 'qcow2')}"
        )

    by_id = {
        s["id"]: s for s in storage_rows if s.get("id") and s.get("directory_path")
    }
    # Parents first: a row that declares one is created as a real overlay on
    # it, so the file on disk carries the chain the row claims.
    for storage in sorted(storage_rows, key=lambda s: bool(s.get("parent"))):
        if storage.get("status") != "ready":
            continue
        directory = storage.get("directory_path")
        storage_id = storage.get("id")
        if not directory or not storage_id:
            continue
        if storage_id in DISKLESS_STORAGE_IDS:
            print(f"Leaving '{storage_id}' fileless on purpose")
            continue
        if not os.path.isdir(directory):
            print(f"Storage dir '{directory}' not mounted; skipping '{storage_id}'")
            continue
        path = _path(storage)
        if os.path.exists(path):
            continue
        parent = by_id.get(storage.get("parent"))
        argv = ["qemu-img", "create", "-f", "qcow2"]
        if parent and os.path.exists(_path(parent)):
            argv += ["-b", _path(parent), "-F", "qcow2", path]
        else:
            argv += [path, str(storage.get("virtual_size") or SEED_DISK_SIZE)]
        try:
            subprocess.run(argv, check=True, capture_output=True)
            print(f"Created placeholder storage file '{path}'")
        except (OSError, subprocess.CalledProcessError) as e:
            print(f"Could not create storage file '{path}': {e}")


def wait_for_hypervisor_online(dbconn, timeout=HYPER_READY_TIMEOUT):
    """Block until a hypervisor can serve storage-pool-gated requests.

    Returns True once an Online + enabled hypervisor with a non-empty storage
    pool exists, or False if the timeout elapses (the suite still runs so the
    failing specs give a clear signal instead of the run hanging).
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            ready = list(
                r.table("hypervisors")
                .filter({"status": "Online", "enabled": True})
                .run(dbconn)
            )
        except Exception as e:
            print(f"Error polling hypervisors: {e}")
            ready = []
        for hyper in ready:
            if hyper.get("enabled_storage_pools") or hyper.get("storage_pools"):
                print(f"Hypervisor '{hyper['id']}' is Online with a storage pool")
                return True
        print("Waiting for an Online+enabled hypervisor with a storage pool...")
        time.sleep(2)
    print(
        f"WARNING: no usable hypervisor after {timeout}s; "
        "storage-pool-dependent tests will likely fail"
    )
    return False


def main():
    dbconn = r.connect(DB_HOST, port=DB_PORT, db=DB_NAME).repl()
    print(f"Connected to RethinkDB {DB_HOST}:{DB_PORT} db={DB_NAME}")

    for table_name in RESET_TABLES:
        try:
            result = r.table(table_name).delete().run(dbconn)
            print(f"Reset table '{table_name}': {result}")
        except Exception as e:
            print(f"Error resetting '{table_name}': {e}")

    for table_name in E2E_PREFIX_TABLES:
        try:
            result = (
                r.table(table_name)
                .filter(r.row["name"].match("^e2e-"))
                .delete()
                .run(dbconn)
            )
            print(f"Cleaned e2e rows from '{table_name}': {result}")
        except Exception as e:
            print(f"Error cleaning e2e rows from '{table_name}': {e}")

    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(".json"):
            continue
        table_name = filename[:-5]
        file_path = os.path.join(DATA_DIR, filename)
        print(f"Inserting data into table '{table_name}' from '{filename}'...")
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            if not isinstance(data, list):
                data = [data]
            result = r.table(table_name).insert(data, conflict="update").run(dbconn)
            print(f"Result: {result}")
            if table_name == "media":
                materialize_media_files(data)
            if table_name == "storage":
                materialize_storage_files(data)
        except Exception as e:
            print(f"Error inserting into '{table_name}': {e}")

    wait_for_hypervisor_online(dbconn)


if __name__ == "__main__":
    main()
