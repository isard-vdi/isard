#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Storage.get_by_path`` must resolve pre-UUID, path-form storage ids."""

from __future__ import annotations

from unittest.mock import patch

from isardvdi_common.models.storage import Storage

LEGACY_ID = "default/default/local/admin-admin/win10-T3_2022-05"
LEGACY_PATH = (
    "/isard/templates/default/default/local/admin-admin/win10-T3_2022-05.qcow2"
)
LEGACY_ROW = {
    "id": LEGACY_ID,
    "directory_path": "/isard/templates",
    "type": "qcow2",
    "status": "ready",
}


def _db(rows):
    """Patch the two primary-key touchpoints ``get_by_path`` reaches."""
    return (
        patch.object(Storage, "exists", side_effect=lambda doc_id: doc_id in rows),
        patch.object(Storage, "get", side_effect=lambda doc_id: rows.get(doc_id)),
    )


def test_get_by_path_resolves_legacy_pathform_id():
    """The row exists under a slash-bearing id; the file's basename does not."""
    exists_p, get_p = _db({LEGACY_ID: LEGACY_ROW})
    with exists_p, get_p:
        found = Storage.get_by_path(LEGACY_PATH)

    assert found is not None
    assert found.id == LEGACY_ID
    assert found.directory_path == "/isard/templates"


def test_get_by_path_still_resolves_uuid_row_via_fast_path():
    """Regression: a normal UUID row (id == file basename) resolves unchanged."""
    uuid = "11111111-2222-3333-4444-555555555555"
    row = {
        "id": uuid,
        "directory_path": "/isard/storage_pools/default/desktops",
        "type": "qcow2",
        "status": "ready",
    }
    path = f"/isard/storage_pools/default/desktops/{uuid}.qcow2"
    exists_p, get_p = _db({uuid: row})
    with exists_p, get_p:
        found = Storage.get_by_path(path)

    assert found is not None
    assert found.id == uuid


def test_get_by_path_returns_none_when_no_row_matches():
    """No row for the file: neither the basename nor any wider split exists."""
    exists_p, get_p = _db({})
    with exists_p, get_p:
        assert Storage.get_by_path(LEGACY_PATH) is None


def test_get_by_path_rejects_split_whose_directory_or_type_disagrees():
    """A coincidental id match needs directory_path and type to rebuild the path."""
    wrong = {
        "id": LEGACY_ID,
        "directory_path": "/isard/groups",  # would reconstruct a different file
        "type": "qcow2",
        "status": "ready",
    }
    exists_p, get_p = _db({LEGACY_ID: wrong})
    with exists_p, get_p:
        assert Storage.get_by_path(LEGACY_PATH) is None
