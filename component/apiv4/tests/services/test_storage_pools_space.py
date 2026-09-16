#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""What the admin storage-pools list says about space, and what it refuses to.

A pool used to be reported by whichever device its root sat on, so any disk
type bind-mounted elsewhere was invisible, and a pool with no mountpoint was
told to check the VDO stats it could never have had.

The redis layer is a fake because these are about which keys get read and what
is done with them, not about redis. The keys themselves are published exactly
as a storage node publishes them.
"""

import pytest
from api.services.storage_pools import StoragePoolService
from isardvdi_common.lib.storage.physical_usage import pool_status_key

MOUNT = "/isard/storage_pools/p"
PATHS = {
    "desktop": [{"path": "groups", "weight": 100}],
    "media": [{"path": "media", "weight": 100}],
    "template": [{"path": "templates", "weight": 100}],
    "volatile": [{"path": "volatile", "weight": 100}],
}


class _FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.reads = []

    def publish(self, path, free, total):
        mapping = {
            "kind": "local-thick",
            "node": "nas-a",
            "source": "statvfs",
            "physical_total_bytes": total,
        }
        if free is not None:
            mapping["physical_free_bytes"] = free
        self.hashes[pool_status_key(path)] = {
            k: str(v).encode() for k, v in mapping.items()
        }

    def hgetall(self, key):
        self.reads.append(key)
        return self.hashes.get(key, {})


@pytest.fixture
def stack(monkeypatch):
    """The service over a fake redis and a caller-supplied set of pools."""
    conn = _FakeRedis()
    monkeypatch.setattr("api.services.storage_pools._redis", lambda: conn)

    def run(pools):
        monkeypatch.setattr(
            "api.services.storage_pools.StoragePoolsProcessed.get_storage_pools",
            staticmethod(lambda: pools),
        )
        return StoragePoolService.get_storage_pools()

    return conn, run, monkeypatch


def test_the_pool_is_judged_by_the_device_that_fails_first(stack):
    """The defect. Media on a nearly-full VDO, everything else on a roomy thick
    disk: the headline figure has to be the VDO's."""
    conn, run, _ = stack
    conn.publish(MOUNT, free=3000, total=4000)
    conn.publish(MOUNT + "/media", free=3, total=200)

    pool = run([{"id": "p", "mountpoint": MOUNT, "paths": PATHS}])[0]

    assert pool["physical_usage"]["physical_free_bytes"] == 3
    assert pool["physical_usage"]["path"] == MOUNT + "/media"
    # And the device that is NOT the constraint is still reported, so an admin
    # can see where the room actually is instead of only that there is none.
    assert [d["path"] for d in pool["physical_usage_devices"]] == [
        MOUNT + "/media",
        MOUNT,
    ]
    assert "physical_usage_reason" not in pool


def test_a_single_device_pool_is_unchanged(stack):
    """The pool that is one filesystem must report exactly what it always did,
    with a one-entry breakdown. If this drifts, every ordinary install's Space
    column drifted with it."""
    conn, run, _ = stack
    conn.publish(MOUNT, free=500, total=1000)

    pool = run([{"id": "p", "mountpoint": MOUNT, "paths": PATHS}])[0]

    assert pool["physical_usage"]["physical_free_bytes"] == 500
    assert pool["physical_usage"]["physical_total_bytes"] == 1000
    assert len(pool["physical_usage_devices"]) == 1


def test_two_disk_types_on_one_device_are_one_device(stack):
    """Counting a shared mount once per disk type would inflate the spread and
    invite a reader to add its capacity to itself."""
    conn, run, _ = stack
    conn.publish(MOUNT, free=900, total=1000)
    conn.publish(MOUNT + "/shared", free=10, total=100)
    paths = {
        "media": [{"path": "shared", "weight": 100}],
        "template": [{"path": "shared", "weight": 100}],
    }

    pool = run([{"id": "p", "mountpoint": MOUNT, "paths": paths}])[0]

    assert len(pool["physical_usage_devices"]) == 2
    shared = pool["physical_usage_devices"][0]
    assert shared["path"] == MOUNT + "/shared"
    assert shared["usages"] == ["shared"]


def test_a_pool_with_no_mountpoint_says_that_and_not_the_other_thing(stack):
    """Two causes, two sentences. Sending this admin to configure
    STORAGE_POOL_VDO_STATS is sending them to fix a machine that was never the
    problem."""
    conn, run, _ = stack

    pool = run([{"id": "p", "mountpoint": "", "paths": PATHS}])[0]

    assert "physical_usage" not in pool
    assert "no mountpoint" in pool["physical_usage_reason"]
    assert "STORAGE_POOL_VDO_STATS" not in pool["physical_usage_reason"]


def test_an_unpublished_pool_names_every_path_it_looked_under(stack):
    """The mountpoint exists and nobody publishes it. Naming the paths turns
    "not reported" into something an operator can go and check."""
    conn, run, _ = stack

    pool = run([{"id": "p", "mountpoint": MOUNT, "paths": PATHS}])[0]

    assert "physical_usage" not in pool
    reason = pool["physical_usage_reason"]
    assert "STORAGE_POOL_VDO_STATS" in reason
    for leaf in ("", "/groups", "/media", "/templates", "/volatile"):
        assert MOUNT + leaf in reason


def test_a_pool_is_never_given_a_figure_that_was_not_measured(stack):
    """No redis at all: no figure, and a reason that says why. A zero here
    would read as a full pool and a made-up total as an empty one."""
    _, run, monkeypatch = stack
    monkeypatch.setattr("api.services.storage_pools._redis", lambda: None)

    pool = run([{"id": "p", "mountpoint": MOUNT, "paths": PATHS}])[0]

    assert "physical_usage" not in pool
    assert "redis" in pool["physical_usage_reason"]
