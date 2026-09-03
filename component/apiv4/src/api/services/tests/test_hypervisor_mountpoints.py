# SPDX-License-Identifier: AGPL-3.0-or-later

"""A pool mount's usage must come from the backing store, not from ``df``.

The engine fills a hypervisor's mountpoints by running ``df`` over ssh. That is
right for the host's own filesystems and wrong for a thin-provisioned pool,
where ``df`` reports the logical size: a pool 60% full of its backing store
showed 9% in this panel, and since the table colours a row red above 90% the
alarm could never fire on the one kind of pool that needs it.
"""

import pytest
from api.services.admin.hypervisors import AdminHypervisorsService


@pytest.fixture
def reported(monkeypatch):
    """Two mounts as the engine reports them: one pool, one plain filesystem."""
    monkeypatch.setattr(
        "api.services.admin.hypervisors.HypervisorsProcessed.get_hyper_mountpoints",
        staticmethod(
            lambda hyper_id: {
                "mountpoints": [
                    {"mount": "/isard/storage_pools/vdo3", "usage": 9},
                    {"mount": "/", "usage": 44},
                ]
            }
        ),
    )


def _published(monkeypatch, mapping):
    monkeypatch.setattr("api.services.admin.hypervisors._redis", lambda: object())
    monkeypatch.setattr(
        "api.services.admin.hypervisors.read_usage",
        lambda connection, mount: mapping.get(mount),
    )


def test_a_measured_pool_mount_reports_the_physical_fill(reported, monkeypatch):
    _published(
        monkeypatch,
        {
            "/isard/storage_pools/vdo3": {
                "thin": True,
                "physical_total_bytes": 100,
                "physical_free_bytes": 40,
            }
        },
    )

    mounts = {m["mount"]: m for m in AdminHypervisorsService.get_hyper_mountpoints("h")}

    pool = mounts["/isard/storage_pools/vdo3"]
    assert pool["usage"] == 60  # not the 9% df reported
    assert pool["physical"] is True
    assert pool["thin"] is True
    # A plain filesystem keeps the figure the engine measured, which is true.
    assert mounts["/"] == {"mount": "/", "usage": 44}


def test_an_unmeasured_mount_is_left_exactly_as_the_engine_reported_it(
    reported, monkeypatch
):
    """Nobody publishing must never turn into a fabricated figure -- it leaves
    the pre-existing behaviour untouched."""
    _published(monkeypatch, {})

    mounts = AdminHypervisorsService.get_hyper_mountpoints("h")

    assert mounts == [
        {"mount": "/isard/storage_pools/vdo3", "usage": 9},
        {"mount": "/", "usage": 44},
    ]


def test_a_measurement_without_a_fill_does_not_overwrite_anything(
    reported, monkeypatch
):
    """A thin pool whose capacity is readable but whose fill is not would
    otherwise divide by a total with no used figure behind it."""
    _published(
        monkeypatch,
        {
            "/isard/storage_pools/vdo3": {
                "thin": True,
                "physical_total_bytes": 100,
                "physical_free_bytes": None,
            }
        },
    )

    mounts = {m["mount"]: m for m in AdminHypervisorsService.get_hyper_mountpoints("h")}

    assert mounts["/isard/storage_pools/vdo3"]["usage"] == 9
    assert "physical" not in mounts["/isard/storage_pools/vdo3"]
