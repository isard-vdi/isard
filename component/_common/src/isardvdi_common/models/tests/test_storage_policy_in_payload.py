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

from unittest.mock import MagicMock, patch

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
