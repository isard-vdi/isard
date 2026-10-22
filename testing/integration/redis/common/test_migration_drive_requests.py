# SPDX-License-Identifier: AGPL-3.0-or-later

"""Real-redis tests for the hand-off from the result consumer to the migration driver."""

import threading
import time

import isardvdi_common.lib.storage.migration_run as mr
import pytest


@pytest.fixture
def conn(scratch_redis, monkeypatch):
    monkeypatch.setattr(mr, "shared_client", lambda *a, **k: scratch_redis)
    return scratch_redis


def _members(conn, key):
    return {m.decode() if isinstance(m, bytes) else m for m in conn.smembers(key)}


def test_requests_keep_their_trees_and_are_taken_once(conn):
    mr.request_drive("m1", tree_ids=["t1"])
    mr.request_drive("m2")
    mr.request_drive("m1", tree_ids=["t2"])

    assert mr._take_drive_requests(conn, 1) == ["m1", "m2"]
    assert conn.llen(mr.DRIVE_REQUESTS_KEY) == 0
    assert _members(conn, "migration:wake:m1") == {"t1", "t2"}
    assert _members(conn, "migration:wake:m2") == {"*"}
    assert mr._take_drive_requests(conn, 1) == []


def test_a_waiting_driver_wakes_as_soon_as_a_request_lands(conn):
    taken = {}

    def _wait():
        start = time.monotonic()
        taken["ids"] = mr._take_drive_requests(conn, 5)
        taken["after_s"] = time.monotonic() - start

    waiter = threading.Thread(target=_wait)
    waiter.start()
    time.sleep(0.3)
    mr.request_drive("m1", tree_ids=["t1"])
    waiter.join(timeout=10)

    assert taken["ids"] == ["m1"]
    assert taken["after_s"] < 2


def test_the_driver_drives_each_requested_migration(conn, monkeypatch):
    driven = []
    monkeypatch.setattr(
        mr,
        "advance",
        lambda mid, *, check_abandon=True, tree_ids=None: driven.append(
            (mid, check_abandon)
        ),
    )
    mr.request_drive("m1", tree_ids=["t1"])
    mr.request_drive("m2")
    mr.request_drive("m1", tree_ids=["t2"])

    passes = iter([False, True])
    mr.serve_drive_requests(block_s=1, stop=lambda: next(passes))

    assert driven == [("m1", False), ("m2", False)]
