# SPDX-License-Identifier: AGPL-3.0-or-later

"""A mass integrity check answers at once and reports every disk; a missing file or a writer damages none."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from typing import Callable, Iterator

import pytest

from .helpers.client import IsardClient
from .helpers.sockets import SocketIOListener
from .helpers.waits import poll_for

rethinkdb = pytest.importorskip("rethinkdb")
from rethinkdb import r  # noqa: E402

pytestmark = [pytest.mark.real, pytest.mark.slow]

READY_TIMEOUT = int(os.environ.get("E2E_CREATE_TIMEOUT", "180"))
CHECK_TIMEOUT = int(os.environ.get("E2E_CHECK_TIMEOUT", "300"))
# the answer carries only the count: queuing the checks happens after it
ANSWER_WITHIN_S = float(os.environ.get("E2E_BULK_CHECK_ANSWER_S", "10"))
TASK_DONE = {"finished", "failed", "canceled"}
OWNER = "local-default-admin-admin"
# the mass check runs on this status, so it reaches this file's own disks
OWN_STATUS = "damaged"

# takes the lock byte a running QEMU holds for write, until the marker file goes
HOLD_WRITE = """
import fcntl, os, struct, sys, time
fd = os.open(sys.argv[1], os.O_RDWR)
fcntl.fcntl(fd, 37, struct.pack("@hhqqi4x", fcntl.F_RDLCK, 0, 101, 1, 0))
open(sys.argv[2], "w").close()
deadline = time.time() + float(sys.argv[3])
while os.path.exists(sys.argv[2]) and time.time() < deadline:
    time.sleep(0.2)
"""


def _connect():
    host = os.environ.get("RETHINKDB_HOST", "isard-db")
    port = int(os.environ.get("RETHINKDB_PORT", "28015"))
    try:
        return r.connect(
            host=host, port=port, db=os.environ.get("RETHINKDB_DB", "isard")
        )
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"RethinkDB not reachable at {host}:{port}: {exc}")


def _in_storage(*args: str) -> list[str]:
    if shutil.which("docker") is None:
        pytest.skip("needs docker to reach the disk files in isard-storage")
    return ["docker", "exec", "isard-storage", *args]


@pytest.fixture
def conn():
    connection = _connect()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def own_disks(admin_client: IsardClient, conn) -> Iterator[Callable[[int], list[str]]]:
    """Blank disks the test creates, alone works on, and deletes."""
    created: list[str] = []

    def make(count: int) -> list[str]:
        new = [
            admin_client.post(
                "/api/v4/item/storage/priority/default",
                json_body={
                    "usage": "desktop",
                    "storage_type": "qcow2",
                    "parent": "",
                    "size": "1G",
                    "user_id": OWNER,
                },
            )["storage_id"]
            for _ in range(count)
        ]
        created.extend(new)
        for storage_id in new:
            poll_for(
                lambda: r.table("storage").get(storage_id).run(conn) or {},
                accept=lambda s: s.get("status") == "ready",
                timeout=READY_TIMEOUT,
                interval=2.0,
                message=f"storage {storage_id} never reached ready",
            )
        return new

    try:
        yield make
    finally:
        for storage_id in created:
            row = r.table("storage").get(storage_id).run(conn)
            if row and row.get("status") in ("ready", OWN_STATUS):
                r.table("storage").get(storage_id).update({"status": "ready"}).run(conn)
                admin_client.raw("DELETE", f"/api/v4/item/storage/{storage_id}")
            elif row:
                r.table("storage").get(storage_id).delete().run(conn)


def _path(conn, storage_id: str) -> str:
    row = r.table("storage").get(storage_id).run(conn)
    return f"{row['directory_path']}/{storage_id}.{row['type']}"


def _row(conn, storage_id: str, accept, message: str) -> dict:
    return poll_for(
        lambda: r.table("storage").get(storage_id).run(conn) or {},
        accept=accept,
        timeout=CHECK_TIMEOUT,
        interval=1.0,
        message=message,
    )


def _check_one(admin_client: IsardClient, storage_id: str) -> dict:
    resp = admin_client.raw("PUT", f"/api/v4/admin/item/storage/{storage_id}/check")
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["task_id"]
    return poll_for(
        lambda: admin_client.get(f"/api/v4/task/{task_id}"),
        accept=lambda t: (t or {}).get("status") in TASK_DONE,
        timeout=CHECK_TIMEOUT,
        interval=1.0,
        message=f"check task {task_id} did not end",
    )


def test_a_mass_check_answers_the_count_at_once_and_reports_every_disk(
    admin_client: IsardClient, ws: SocketIOListener, conn, own_disks
):
    ours = own_disks(3)
    others = set(r.table("storage").get_all(OWN_STATUS, index="status")["id"].run(conn))
    for storage_id in ours:
        r.table("storage").get(storage_id).update(
            {"status": OWN_STATUS, "damage_reason": "seeded by the integration test"}
        ).run(conn)
    accepted = len(others - set(ours)) + len(ours)

    started = time.monotonic()
    resp = admin_client.raw("PUT", f"/api/v4/admin/items/storage/check/{OWN_STATUS}")
    took = time.monotonic() - started
    assert resp.status_code == 202, resp.text
    assert took < ANSWER_WITHIN_S, f"the mass check answered after {took:.1f}s"
    assert resp.json() == {"status": OWN_STATUS, "accepted": accepted}

    def notice():
        for ns, event, payload in ws.snapshot():
            if (
                ns == "/administrators"
                and event == "msg"
                and isinstance(payload, dict)
                and payload.get("title")
                == f"Integrity checks of the {OWN_STATUS} disks"
            ):
                return payload
        return None

    payload = poll_for(
        notice,
        accept=lambda p: p is not None,
        timeout=CHECK_TIMEOUT,
        interval=1.0,
        message="no notice said how the mass check ended",
    )
    first, *refusals = payload["description"].split("\n")
    assert first.endswith(f" of {accepted} disk(s)."), first
    queued = int(first.split()[2])
    refused = sum(int(line.split()[0]) for line in refusals)
    assert queued + refused == accepted, payload["description"]
    for storage_id in ours:
        row = _row(
            conn,
            storage_id,
            lambda s: s.get("status") == "ready" and s.get("last_checked_at"),
            f"storage {storage_id} got no sound verdict from the mass check",
        )
        assert not row.get("damage_reason"), row


def test_a_check_of_a_disk_without_file_flags_it_for_review(
    admin_client: IsardClient, conn, own_disks
):
    [storage_id] = own_disks(1)
    path = _path(conn, storage_id)
    subprocess.run(_in_storage("rm", "-f", path), check=True)
    try:
        _check_one(admin_client, storage_id)
        row = _row(
            conn,
            storage_id,
            lambda s: "review_coherence" in (s.get("pending_actions") or {}),
            f"storage {storage_id} without file got no review mark",
        )
        mark = row["pending_actions"]["review_coherence"]
        assert mark["found_by"] == "check_integrity", mark
        assert mark["detail"]["path"] == path, mark
        # one absent read never takes a disk out of service, nor reads as damage
        assert row["status"] == "ready", row["status"]
    finally:
        # a row without file leaves the table directly, not through a delete task
        r.table("storage").get(storage_id).update({"status": "orphan"}).run(conn)


def test_a_check_while_a_writer_holds_the_image_records_no_verdict(
    admin_client: IsardClient, conn, own_disks
):
    [storage_id] = own_disks(1)
    path = _path(conn, storage_id)
    before = r.table("storage").get(storage_id).run(conn).get("last_checked_at")
    marker = f"/tmp/hold-{uuid.uuid4().hex}"
    holder = subprocess.Popen(
        _in_storage("python3", "-c", HOLD_WRITE, path, marker, "600")
    )
    try:
        poll_for(
            lambda: subprocess.run(_in_storage("test", "-f", marker)).returncode,
            accept=lambda rc: rc == 0,
            timeout=30,
            interval=0.5,
            message="the writer never took the image's lock",
        )
        _check_one(admin_client, storage_id)
        row = _row(
            conn,
            storage_id,
            lambda s: "check_inconclusive" in (s.get("pending_actions") or {}),
            f"storage {storage_id} checked under a writer left no mark",
        )
        assert (
            "open for writing"
            in row["pending_actions"]["check_inconclusive"]["detail"]["summary"]
        ), row["pending_actions"]
        assert row["status"] == "ready", row["status"]
        assert row.get("last_checked_at") == before, row
    finally:
        subprocess.run(_in_storage("rm", "-f", marker))
        holder.wait(timeout=30)

    _check_one(admin_client, storage_id)
    row = _row(
        conn,
        storage_id,
        lambda s: "check_inconclusive" not in (s.get("pending_actions") or {}),
        f"storage {storage_id} kept the inconclusive mark once the writer left",
    )
    assert row.get("last_checked_at"), row
    assert row["status"] == "ready", row["status"]
