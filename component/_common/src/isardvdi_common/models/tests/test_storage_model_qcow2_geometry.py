#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``StorageModel`` documents the ``qcow2_geometry`` sub-document.

The field is written on the ``storage`` row through the task-result path
(``init_document``), which bypasses pydantic, so nothing enforces the shape
today. Declaring it on ``StorageModel`` is documentation with a type on it:
the day someone wires ``_rdb_table_schema = StorageModel`` the key survives
instead of being silently dropped. These pin that the field exists, defaults to
absent, and round-trips a geometry sub-document.
"""

from isardvdi_common.models.storage import StorageModel


def _row(**extra):
    base = dict(
        usage="desktop",
        parent=None,
        size="10G",
        perms=["r", "w"],
        directory_path="/isard/groups",
        status="ready",
        status_time=None,
        task=None,
        type="qcow2",
    )
    base.update(extra)
    return StorageModel(**base)


def test_geometry_defaults_to_absent():
    # A registry download or a pre-field row carries no geometry: absence is an
    # acceptable signal, not an error.
    assert _row().qcow2_geometry is None


def test_geometry_round_trips_a_sub_document():
    geo = {
        "cluster_size": "128k",
        "extended_l2": "on",
        "lazy_refcounts": "on",
        "preallocation": "metadata",
    }
    row = _row(qcow2_geometry=geo)
    assert row.qcow2_geometry == geo
    assert row.model_dump()["qcow2_geometry"] == geo
