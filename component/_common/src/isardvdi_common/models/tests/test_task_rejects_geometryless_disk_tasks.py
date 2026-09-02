#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A disk-writing task must carry the qcow2 geometry, or never reach RQ.

``Task.__init__`` is the only seam that sees every created task -- roots and
nested dependents alike, because the dependents loop recurses through
``Task(**dependent)``. The guard there turns "a create/convert/disconnect
arriving without the geometry" from a worker-side ``TypeError`` after N retries
into an immediate, attributable ``ValueError`` inside the request that produced
it.
"""

from unittest.mock import MagicMock, patch

import pytest
from isardvdi_common.helpers import qcow2_geometry
from isardvdi_common.models.task import Task, _require_qcow2_geometry

_GEO = {
    "cluster_size": "4k",
    "extended_l2": "off",
    "lazy_refcounts": "off",
    "preallocation": "off",
}


# --- the helper in isolation -------------------------------------------------


class TestRequireHelper:
    @pytest.mark.parametrize("task", ["create", "convert", "disconnect"])
    @pytest.mark.parametrize("missing", list(qcow2_geometry.KEYS))
    def test_a_disk_task_missing_a_key_raises(self, task, missing):
        kwargs = {k: v for k, v in _GEO.items() if k != missing}
        with pytest.raises(ValueError, match="qcow2 geometry"):
            _require_qcow2_geometry(task, kwargs)

    @pytest.mark.parametrize("task", ["create", "convert", "disconnect"])
    def test_a_disk_task_with_all_keys_passes(self, task):
        _require_qcow2_geometry(task, dict(_GEO))  # must not raise

    def test_a_non_disk_task_needs_no_geometry(self):
        _require_qcow2_geometry("find", {})  # must not raise
        _require_qcow2_geometry("move", {"origin_path": "/a"})  # must not raise
        _require_qcow2_geometry(None, {})  # must not raise


# --- wired into Task construction --------------------------------------------


def _task(**kwargs):
    with patch.object(Task, "_redis", MagicMock()):
        return Task(**kwargs)


class TestWiredIntoTask:
    def test_a_create_without_geometry_never_reaches_rq(self):
        with pytest.raises(ValueError, match="qcow2 geometry"):
            _task(
                task="create",
                queue="storage.p.default",
                job_kwargs={
                    "kwargs": {
                        "storage_path": "/isard/g/d.qcow2",
                        "storage_type": "qcow2",
                    }
                },
            )

    def test_a_find_without_geometry_is_fine(self):
        # A positive control: a non-disk task builds without geometry. Guarded
        # so it never enqueues (no live Redis in the test).
        built = _task(
            task="find",
            queue="storage.p.default",
            enqueue=False,
            job_kwargs={"kwargs": {"storage_path": "/isard/g/d.qcow2"}},
        )
        assert built.job is not None

    def test_a_nested_create_dependent_without_geometry_raises(self):
        # Site 6's shape: a create hung under a move root. The guard must fire
        # on the nested dependent, not only on roots.
        with pytest.raises(ValueError, match="qcow2 geometry"):
            _task(
                task="move",
                queue="storage.p.default",
                enqueue=False,
                job_kwargs={"kwargs": {"origin_path": "/a", "destination_path": "/b"}},
                dependents=[
                    {
                        "queue": "storage.p.default",
                        "task": "create",
                        "job_kwargs": {
                            "kwargs": {
                                "storage_path": "/isard/g/d.qcow2",
                                "storage_type": "qcow2",
                            }
                        },
                    }
                ],
            )
