# SPDX-License-Identifier: AGPL-3.0-or-later

"""A convert chain carries the step that removes the destination when it does not finish."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from isardvdi_common.models import storage as _storage


def _chain():
    origin = SimpleNamespace(
        id="s-1",
        path="/isard/groups/u/s-1.qcow2",
        directory_path="/isard/groups/u",
        set_maintenance=MagicMock(),
        create_task=MagicMock(return_value="t-1"),
    )
    new_storage = SimpleNamespace(
        id="s-2", path="/isard/groups/u/s-2.vmdk", directory_path="/isard/groups/u"
    )
    with (
        patch.object(
            _storage.StoragePool,
            "get_best_for_action",
            return_value=SimpleNamespace(id="default"),
        ),
        patch.object(_storage.qcow2_geometry, "policy", return_value={}),
        patch.object(_storage, "storage_min_free_bytes", return_value=0),
    ):
        _storage.Storage.convert(origin, "u-1", new_storage, "vmdk", "ready", False)
    return origin.create_task.call_args.kwargs["dependents"]


def test_the_destination_is_discarded_by_a_direct_dependent():
    steps = {step["task"]: step for step in _chain()}
    discard = steps["convert_discard_destination"]
    assert discard["queue"] == "core"
    assert discard["job_kwargs"]["kwargs"] == {
        "storage_id": "s-2",
        "path": "/isard/groups/u/s-2.vmdk",
    }
    # a direct dependent sees the convert's own outcome, as update_status does
    assert "update_status" in steps
