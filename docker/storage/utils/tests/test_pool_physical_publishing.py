#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Only the node that owns a pool's backing store may publish its usage.

Publishing is keyed by mountpoint and every publisher writes the same key, so
whoever writes last wins. A worker that mounts the pool over the network can
measure nothing, and if it published that "nothing" it would erase the real
measurement taken by the node holding the physical mounts -- turning the number
every free-space decision depends on into a race between reporters.

Also pinned here: the reporter reaches no database. It enumerates its own mounts
and writes to redis, because this container must never talk to RethinkDB.
"""

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip(
    "isardvdi_common.lib.storage.physical_usage",
    reason="the reporter measures through _common",
)


def _load():
    """The tool ships without a .py suffix, so it is loaded by path."""
    path = Path(__file__).resolve().parents[1] / "storage-pool-physical"
    spec = importlib.util.spec_from_loader(
        "storage_pool_physical",
        importlib.machinery.SourceFileLoader("storage_pool_physical", str(path)),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reporter = _load()

LOCAL = "/isard/storage_pools/vdo3"
REMOTE = "/isard/storage_pools/nfs"


@pytest.fixture
def wired(monkeypatch):
    """Wire the reporter to scripted measurements and a recording publisher."""
    published = {}

    measured = {
        LOCAL: {
            "kind": "local-thin",
            "thin": True,
            "backend": "lvm-vdo",
            "fstype": "xfs",
            "mount_point": LOCAL,
            "path": LOCAL,
            "physical_total_bytes": 18630494388224,
            "physical_used_bytes": 123565072384,
            "physical_free_bytes": 18506929315840,
            "filesystem_free_bytes": 91345006592000,
            "reason": "thin",
        },
        REMOTE: {
            "kind": "network",
            "thin": False,
            "backend": None,
            "fstype": "nfs4",
            "mount_point": REMOTE,
            "path": REMOTE,
            "physical_total_bytes": None,
            "physical_used_bytes": None,
            "physical_free_bytes": None,
            "filesystem_free_bytes": 12345,
            "reason": "served by another host",
        },
    }

    monkeypatch.setattr(reporter, "pool_paths", lambda: [LOCAL, REMOTE])
    monkeypatch.setattr(reporter, "vdo_status", lambda *a, **k: {})
    monkeypatch.setattr(
        reporter, "pool_physical_usage", lambda path, **kwargs: dict(measured[path])
    )
    monkeypatch.setattr(
        reporter,
        "publish_usage",
        lambda connection, usage, ttl: published.setdefault(
            usage["path"], (usage, ttl)
        ),
    )
    monkeypatch.setenv("STORAGE_DOMAIN", "storage-1")
    return published


def test_a_network_pool_is_measured_but_never_published(wired):
    results = reporter.cycle(connection=object(), ttl=900)

    # It is still measured and logged -- an operator has to be able to see why
    # this node is not the one reporting.
    assert results[REMOTE]["kind"] == "network"
    assert REMOTE not in wired


def test_the_owning_node_publishes_and_stamps_itself(wired):
    reporter.cycle(connection=object(), ttl=900)

    usage, ttl = wired[LOCAL]
    assert usage["physical_free_bytes"] == 18506929315840
    assert usage["node"] == "storage-1"
    assert ttl == 900


def test_json_mode_publishes_nothing(wired):
    results = reporter.cycle()

    assert set(results) == {LOCAL, REMOTE}
    assert wired == {}


def test_thin_pool_without_a_fill_is_flagged_to_the_operator(
    wired, monkeypatch, caplog
):
    """A thin pool whose fill is unknown must say what to do about it.

    Silence reads as "measured, nothing to see": the published key would carry a
    capacity and no fill, and the reason would live only in the log nobody read.
    """
    blind = {
        "kind": "local-thin",
        "thin": True,
        "backend": "lvm-vdo",
        "fstype": "xfs",
        "mount_point": LOCAL,
        "path": LOCAL,
        "physical_total_bytes": 18630494388224,
        "physical_used_bytes": None,
        "physical_free_bytes": None,
        "filesystem_free_bytes": 91345006592000,
        "reason": "needs the device-mapper ioctl",
    }
    monkeypatch.setattr(reporter, "pool_paths", lambda: [LOCAL])
    monkeypatch.setattr(reporter, "pool_physical_usage", lambda path, **k: dict(blind))

    with caplog.at_level("WARNING"):
        reporter.cycle(connection=object(), ttl=900)

    assert "STORAGE_POOL_PHYSICAL_STATS" in caplog.text


def test_the_reporter_never_reaches_a_database():
    """The rule this whole shape exists for: isard-storage talks to redis only.

    A future edit that pulls the pool list from RethinkDB would look harmless
    and would reintroduce a dependency the container must not have, so it is
    asserted against the source rather than left to review.
    """
    source = (Path(__file__).resolve().parents[1] / "storage-pool-physical").read_text()
    for forbidden in ("rethinkdb", "RethinkDB", "Processed", "models.storage"):
        assert (
            forbidden not in source.split('"""')[2]
        ), f"{forbidden} must not appear in the reporter's code"
