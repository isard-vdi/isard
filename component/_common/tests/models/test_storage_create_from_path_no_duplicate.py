#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Storage.create_from_path`` returns the existing row instead of a duplicate."""

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
    return (
        patch.object(Storage, "exists", side_effect=lambda doc_id: doc_id in rows),
        patch.object(Storage, "get", side_effect=lambda doc_id: rows.get(doc_id)),
    )


def test_create_from_path_returns_existing_legacy_row_not_a_duplicate():
    """A file already owned by a path-form row resolves to that row, with no insert."""
    exists_p, get_p = _db({LEGACY_ID: LEGACY_ROW})
    with exists_p, get_p, patch.object(Storage, "init_document") as init_doc:
        result = Storage.create_from_path(LEGACY_PATH, user_id="u1")

    init_doc.assert_not_called()
    assert result is not None
    assert result.id == LEGACY_ID


def test_create_from_path_still_creates_when_file_has_no_row():
    """Regression: with no row for the file, it must still create one."""
    sentinel = object()
    exists_p, get_p = _db({})
    with exists_p, get_p, patch.object(
        Storage, "init_document", return_value=sentinel
    ) as init_doc:
        result = Storage.create_from_path(LEGACY_PATH, user_id="u1")

    init_doc.assert_called_once()
    assert result is sentinel
