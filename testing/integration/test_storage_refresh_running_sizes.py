# SPDX-License-Identifier: AGPL-3.0-or-later

"""Real-stack e2e for the running-desktop disk-size refresh sweep.

``POST /admin/storage/refresh-running-sizes`` re-measures ``qemu-img-info``
for the disks of currently-running desktops, so a long-running desktop's
stored ``actual-size`` does not stay frozen at its last stop.

There is no public API to put a desktop into the ``Started`` state with a
stale stored size without booting a real VM (impossible under
``E2E_SKIP_VM_BOOT``), so this test seeds the exact scenario directly in
RethinkDB and asserts the endpoint's *selection + enqueue* behaviour
through the real apiv4 + isard-storage stack:

  - a ``Started`` desktop's ready, non-readonly disk -> refresh enqueued
  - that same desktop's read-only disk               -> skipped
  - a ``Stopped`` desktop's ready disk               -> skipped

The deep "the worker re-measures the real qcow2 and the stored
actual-size becomes correct" proof needs a real file + storage worker on
disk and is covered on the staging testbed; here we assert the endpoint
reports an enqueue and that exactly the eligible disk received a refresh
task (its ``task`` field is set), through the live endpoint.
"""

from __future__ import annotations

import os
import uuid

import pytest
from isardvdi_common.lib.task_index import current_task_id
from isardvdi_common.models.task import Task

rethinkdb = pytest.importorskip("rethinkdb")
from rethinkdb import r  # noqa: E402

REFRESH_URL = "/api/v4/admin/storage/refresh-running-sizes"
DEFAULT_POOL_ID = "00000000-0000-0000-0000-000000000000"


def _connect():
    host = os.environ.get("RETHINKDB_HOST", "isard-db")
    port = int(os.environ.get("RETHINKDB_PORT", "28015"))
    db = os.environ.get("RETHINKDB_DB", "isard")
    try:
        return r.connect(host=host, port=port, db=db)
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"RethinkDB not reachable at {host}:{port}: {exc}")


def _desktop_dir(conn) -> str:
    pool = r.table("storage_pool").get(DEFAULT_POOL_ID).run(conn)
    mount = (pool or {}).get("mountpoint", "/isard")
    return f"{mount}/groups"


def _storage_doc(sid, user_id, directory_path, readonly=False):
    doc = {
        "id": sid,
        "status": "ready",
        "directory_path": directory_path,
        "type": "qcow2",
        "user_id": user_id,
        "task": None,
        "parent": None,
        "usage": "desktop",
        "size": "64",
        "perms": ["r", "w"],
        "status_logs": [],
        "status_time": None,
        "qemu-img-info": {
            "virtual-size": 67108864,
            "actual-size": 4096,  # deliberately stale/wrong
            "cluster-size": 65536,
            "filename": f"{directory_path}/{sid}.qcow2",
            "format": "qcow2",
            "backing-filename": None,
            "full-backing-filename": None,
            "backing-filename-format": None,
        },
    }
    if readonly:
        doc["readonly"] = True
    return doc


@pytest.mark.real
def test_refresh_running_sizes_selects_only_running_ready_nonreadonly_disks(
    admin_client,
):
    conn = _connect()
    user_id = admin_client.user_id
    sfx = uuid.uuid4().hex[:8]
    directory_path = _desktop_dir(conn)

    sid_ready = f"e2e_refresh_ready_{sfx}"
    sid_readonly = f"e2e_refresh_ro_{sfx}"
    sid_stopped = f"e2e_refresh_stopped_{sfx}"
    dom_started = f"e2e_refresh_started_{sfx}"
    dom_stopped = f"e2e_refresh_stopped_dom_{sfx}"

    try:
        r.table("storage").insert(
            [
                _storage_doc(sid_ready, user_id, directory_path),
                _storage_doc(sid_readonly, user_id, directory_path, readonly=True),
                _storage_doc(sid_stopped, user_id, directory_path),
            ],
            conflict="replace",
        ).run(conn)
        r.table("domains").insert(
            [
                {
                    "id": dom_started,
                    "kind": "desktop",
                    "name": dom_started,
                    "status": "Started",
                    "user": user_id,
                    "hardware": {
                        "disks": [
                            {"storage_id": sid_ready},
                            {"storage_id": sid_readonly},
                        ]
                    },
                },
                {
                    "id": dom_stopped,
                    "kind": "desktop",
                    "name": dom_stopped,
                    "status": "Stopped",
                    "user": user_id,
                    "hardware": {"disks": [{"storage_id": sid_stopped}]},
                },
            ],
            conflict="replace",
        ).run(conn)

        result = admin_client.post(REFRESH_URL)
        assert isinstance(result, dict), result
        # At least our running desktop's ready disk; other running desktops
        # in the environment may add to the count.
        assert result.get("enqueued", 0) >= 1

        # Asked of the task index, not the row: the ``task`` scalar is retired
        # and no longer written, so reading it would call every disk untouched
        # and this assertion would pass or fail for the wrong reason.
        tasks = {
            sid: current_task_id(Task._redis, sid)
            for sid in (sid_ready, sid_readonly, sid_stopped)
        }
        # Only the running desktop's ready, non-readonly disk got a refresh.
        assert tasks[sid_ready], f"ready disk not refreshed: {tasks}"
        assert tasks[sid_readonly] is None, f"read-only disk refreshed: {tasks}"
        assert tasks[sid_stopped] is None, f"stopped desktop disk refreshed: {tasks}"
    finally:
        r.table("storage").get_all(sid_ready, sid_readonly, sid_stopped).delete().run(
            conn
        )
        r.table("domains").get_all(dom_started, dom_stopped).delete().run(conn)
        conn.close()
