#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards in front of ``restore`` — the recovery path that re-inserts users,
groups and categories and flips disks back to ``ready``.

Restoring an entry that is already ``deleted`` (its disks are gone) or letting
a user restore *itself* both corrupt state, so ``restore`` and its helper
``check_can_restore`` refuse them up front. Each guard must go red when
inverted.
"""

import pytest


def _bare_entry(**attrs):
    from isardvdi_common.helpers.recycle_bin import RecycleBin

    rb = RecycleBin.__new__(RecycleBin)
    for k, v in attrs.items():
        setattr(rb, k, v)
    return rb


class TestRestoreRefusesTerminalStatus:
    """A ``deleted`` entry has no disks left to restore and a ``restored`` one
    is already back; ``restore`` must refuse both before touching the DB."""

    @pytest.mark.parametrize("status", ["deleted", "restored"])
    def test_refuses_a_terminal_entry(self, status):
        from isardvdi_common.helpers.recycle_bin import Error

        rb = _bare_entry(status=status)
        with pytest.raises(Error) as exc:
            rb.restore()
        assert exc.value.status_code == 428
        assert exc.value.error["error"] == "precondition_required"
        assert status in exc.value.error["description"]


class TestCheckCanRestoreUserByItself:
    """A ``user`` entry whose owner is the agent doing the restore would let a
    user un-delete itself mid-operation. ``check_can_restore`` forbids it."""

    def test_user_cannot_restore_itself(self):
        from isardvdi_common.helpers.recycle_bin import Error

        rb = _bare_entry(
            item_type="user",
            owner_id="u1",
            agent_id="u1",
            owner_name="alice",
        )
        with pytest.raises(Error) as exc:
            rb.check_can_restore()
        assert exc.value.status_code == 400
        assert "by itself" in exc.value.error["description"]

    def test_a_different_agent_is_allowed_past_this_guard(self):
        """Owner != agent must NOT trip the self-restore guard. With empty
        item collections it sails past every check and returns None."""
        rb = _bare_entry(
            item_type="user",
            owner_id="u1",
            agent_id="admin-99",
            owner_name="alice",
            desktops=[],
            templates=[],
            deployments=[],
            users=[],
            categories=[],
            groups=[],
        )
        assert rb.check_can_restore() is None
