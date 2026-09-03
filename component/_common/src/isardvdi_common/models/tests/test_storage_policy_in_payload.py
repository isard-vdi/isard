#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The enqueue sites carry the RESOLVED policy values, not just the shape.

The AST exhaustiveness test proves every disk task spreads ``**geometry``, but
it never resolves what ``geometry`` is bound to -- it stays green even if
``policy()`` returned ``{}``. These drive the real method bodies with a live
environment and assert the actual values (geometry AND ``min_free_bytes``) reach
the task payload, so a broken ``policy()`` or a dropped floor fails loudly.
"""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from isardvdi_common.helpers import qcow2_geometry
from isardvdi_common.models.storage import Storage


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    qcow2_geometry._cached = None
    monkeypatch.setenv("QCOW2_CLUSTER_SIZE", "128k")
    monkeypatch.setenv("QCOW2_EXTENDED_L2", "on")
    monkeypatch.setenv("QCOW2_LAZY_REFCOUNTS", "on")
    monkeypatch.setenv("QCOW2_PREALLOCATION", "off")
    monkeypatch.setenv("STORAGE_MIN_FREE_BYTES", "5368709120")  # 5 GiB
    yield
    qcow2_geometry._cached = None


def _bare(id="s1"):
    s = Storage.__new__(Storage)
    for k, v in {
        "id": id,
        "directory_path": "/isard/groups",
        "type": "qcow2",
        "user_id": "u1",
        "parent": None,
        "task": None,
    }.items():
        object.__setattr__(s, k, v)
    return s


_EXPECTED_GEO = {
    "cluster_size": "128k",
    "extended_l2": "on",
    "lazy_refcounts": "on",
    "preallocation": "off",
}


def _measures(call_kwargs):
    """Every ``qemu_img_info_backing_chain`` dependent's kwargs in the chain."""
    out = []

    def _walk(deps):
        for dep in deps or []:
            if dep.get("task") == "qemu_img_info_backing_chain":
                out.append(dep.get("job_kwargs", {}).get("kwargs", {}))
            _walk(dep.get("dependents"))

    _walk(call_kwargs.get("dependents"))
    return out


def _capture_disconnect():
    s = _bare()
    with (
        patch.object(Storage, "create_task") as mock_create,
        patch.object(Storage, "set_maintenance"),
        patch("isardvdi_common.models.storage.StoragePool") as mock_pool,
    ):
        mock_pool.get_best_for_action.return_value = MagicMock(id="poolA")
        s.disconnect_chain(user_id="u1")
    return mock_create.call_args.kwargs


def test_disconnect_payload_carries_the_resolved_geometry_values():
    kwargs = _capture_disconnect()["job_kwargs"]["kwargs"]
    for key, value in _EXPECTED_GEO.items():
        assert kwargs[key] == value


def test_disconnect_payload_carries_the_resolved_floor():
    kwargs = _capture_disconnect()["job_kwargs"]["kwargs"]
    assert kwargs["min_free_bytes"] == 5368709120


def test_disconnect_measure_records_the_geometry():
    measures = _measures(_capture_disconnect())
    stamped = [m for m in measures if "qcow2_geometry" in m]
    assert stamped, "the disconnect measure must record the applied geometry"
    assert stamped[0]["qcow2_geometry"] == _EXPECTED_GEO


def _capture_convert(new_storage_type="qcow2"):
    s = _bare("src")
    dest = _bare("dst")
    with (
        patch.object(Storage, "create_task") as mock_create,
        patch.object(Storage, "set_maintenance"),
        patch("isardvdi_common.models.storage.StoragePool") as mock_pool,
    ):
        mock_pool.get_best_for_action.return_value = MagicMock(id="poolA")
        s.convert(
            user_id="u1",
            new_storage=dest,
            new_storage_type=new_storage_type,
            new_storage_status="ready",
            compress=False,
        )
    return mock_create.call_args.kwargs


def test_convert_payload_carries_the_resolved_geometry_and_floor():
    kwargs = _capture_convert()["job_kwargs"]["kwargs"]
    for key, value in _EXPECTED_GEO.items():
        assert kwargs[key] == value
    assert kwargs["min_free_bytes"] == 5368709120


def test_convert_qcow2_measure_records_the_geometry():
    measures = _measures(_capture_convert("qcow2"))
    stamped = [m for m in measures if "qcow2_geometry" in m]
    assert stamped, "a qcow2 convert must record the applied geometry"
    assert stamped[0]["qcow2_geometry"] == _EXPECTED_GEO


def test_convert_vmdk_measure_records_no_geometry():
    measures = _measures(_capture_convert("vmdk"))
    assert measures, "the vmdk convert still measures its destination"
    assert all("qcow2_geometry" not in m for m in measures)


def test_create_new_storage_payload_carries_the_resolved_geometry():
    """create_new_storage is the enqueue site behind every new blank/parented
    desktop disk. Drive the real body and assert the RESOLVED values reach the
    payload -- the AST test alone would stay green with a hardcoded literal."""
    disk = _bare("disk-1")
    with (
        patch.object(
            Storage, "create_task", return_value=MagicMock(id="job-1")
        ) as mock_create,
        patch.object(Storage, "new_dict", return_value=disk),
        patch.object(Storage, "set_maintenance"),
        patch.object(
            Storage, "pool", new_callable=PropertyMock, return_value=MagicMock(id="pA")
        ),
        patch.object(Storage, "__setattr__", lambda self, name, value: None),
    ):
        Storage.create_new_storage(
            user_id="u1", pool_usage="desktop", parent_id=None, size="10"
        )
    kwargs = mock_create.call_args.kwargs["job_kwargs"]["kwargs"]
    for key, value in _EXPECTED_GEO.items():
        assert kwargs[key] == value


def test_mv_move_carries_the_resolved_floor():
    """The mv move site (a same-fs rename skips the gate, but the payload must
    still carry the enqueuer-resolved floor, not fall back to the worker env)."""
    s = _bare()
    with (
        patch.object(Storage, "create_task") as mock_create,
        patch.object(Storage, "set_maintenance"),
        patch.object(
            Storage, "pool", new_callable=PropertyMock, return_value=MagicMock(id="pA")
        ),
        patch.object(
            Storage, "domains", new_callable=PropertyMock, return_value=[], create=True
        ),
        patch("isardvdi_common.models.storage.StoragePool") as mock_pool,
        patch(
            "isardvdi_common.models.storage.get_queue_from_storage_pools",
            return_value="pA",
        ),
    ):
        mock_pool.get_best_for_action.return_value = MagicMock(id="pA")
        s.mv(user_id="u1", destination_path="/isard/templates")
    kwargs = mock_create.call_args.kwargs["job_kwargs"]["kwargs"]
    assert kwargs["min_free_bytes"] == 5368709120


def test_a_malformed_floor_raises_before_flipping_maintenance(monkeypatch):
    """The resolve-before-maintenance ordering IS the fix: a malformed value must
    raise BEFORE the row is flipped, or the disk is stuck in maintenance with no
    task to clear it."""
    monkeypatch.setenv("STORAGE_MIN_FREE_BYTES", "1G")  # human-readable typo
    s = _bare()
    flips = []
    with (
        patch.object(Storage, "create_task"),
        patch.object(
            Storage, "set_maintenance", lambda self, action: flips.append(action)
        ),
        patch("isardvdi_common.models.storage.StoragePool") as mock_pool,
    ):
        mock_pool.get_best_for_action.return_value = MagicMock(id="poolA")
        with pytest.raises(ValueError, match="STORAGE_MIN_FREE_BYTES"):
            s.disconnect_chain(user_id="u1")
    assert flips == []  # never flipped to maintenance


def test_a_bad_geometry_raises_before_flipping_maintenance(monkeypatch):
    monkeypatch.setenv("QCOW2_CLUSTER_SIZE", "4k")
    monkeypatch.setenv("QCOW2_EXTENDED_L2", "on")  # invalid with a 4k cluster
    s = _bare()
    flips = []
    with (
        patch.object(Storage, "create_task"),
        patch.object(
            Storage, "set_maintenance", lambda self, action: flips.append(action)
        ),
        patch("isardvdi_common.models.storage.StoragePool") as mock_pool,
    ):
        mock_pool.get_best_for_action.return_value = MagicMock(id="poolA")
        with pytest.raises(ValueError):
            s.disconnect_chain(user_id="u1")
    assert flips == []


def test_rsync_move_carries_the_resolved_floor():
    """move is the third whole-disk copy and gates on the same floor; it must
    carry it from the enqueuer, not read it from the worker's own env."""
    s = _bare()
    with (
        patch.object(Storage, "create_task") as mock_create,
        patch.object(Storage, "set_maintenance"),
        patch.object(
            Storage, "pool", new_callable=PropertyMock, return_value=MagicMock(id="pA")
        ),
        patch.object(
            Storage,
            "status",
            new_callable=PropertyMock,
            return_value="ready",
            create=True,
        ),
        patch("isardvdi_common.models.storage.StoragePool") as mock_pool,
        patch(
            "isardvdi_common.models.storage.get_queue_from_storage_pools",
            return_value="pA",
        ),
    ):
        mock_pool.get_best_for_action.return_value = MagicMock(id="pA")
        s.rsync(user_id="u1", destination_path="/isard/templates/x.qcow2")
    kwargs = mock_create.call_args.kwargs["job_kwargs"]["kwargs"]
    assert kwargs["min_free_bytes"] == 5368709120
