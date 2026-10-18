# SPDX-License-Identifier: AGPL-3.0-or-later

"""increase_size refuses a read-only row or one with dependents before it ever
puts the disk into maintenance or enqueues a resize."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models.storage import Storage


def _bare(perms):
    s = Storage.__new__(Storage)
    for k, v in {
        "id": "s1",
        "directory_path": "/isard/groups",
        "type": "qcow2",
        "user_id": "u1",
        "perms": perms,
        "status": "ready",
        "task": None,
    }.items():
        object.__setattr__(s, k, v)
    return s


def test_increase_refuses_a_read_only_row():
    s = _bare(["r"])
    with (
        patch.object(Storage, "create_task") as ct,
        patch.object(Storage, "set_maintenance") as sm,
        patch.object(Storage, "dependents", return_value=[]),
    ):
        with pytest.raises(Error):
            s.increase_size("u1", 1)
    ct.assert_not_called()
    sm.assert_not_called()


def test_increase_refuses_a_row_with_dependents():
    s = _bare(["r", "w"])
    with (
        patch.object(Storage, "create_task") as ct,
        patch.object(Storage, "set_maintenance") as sm,
        patch.object(Storage, "dependents", return_value=[MagicMock()]),
    ):
        with pytest.raises(Error):
            s.increase_size("u1", 1)
    ct.assert_not_called()
    sm.assert_not_called()
