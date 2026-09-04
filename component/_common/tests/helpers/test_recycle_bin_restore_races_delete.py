#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A restore must not be able to outrun the delete it races.

The entry's status is snapshotted once at construction and `check_can_restore`
costs many round trips, so a guard that only reads that snapshot decides on a
value the delete chain has already moved on from.
"""

from unittest.mock import MagicMock, patch

import pytest


def _bare_entry(**attrs):
    from isardvdi_common.helpers.recycle_bin import RecycleBin

    rb = RecycleBin.__new__(RecycleBin)
    for k, v in attrs.items():
        setattr(rb, k, v)
    return rb


class TestOnlyARecycledEntryCanBeRestored:
    @pytest.mark.parametrize("status", ["queued", "deleting"])
    def test_an_entry_being_deleted_is_refused_before_the_database(self, status):
        """``queued`` and ``deleting`` mean the delete is already in flight, and
        the old guard let both through because it only excluded the two terminal
        statuses."""
        from isardvdi_common.helpers.recycle_bin import Error

        rb = _bare_entry(status=status, id="rb1", owner_id="u1", item_type="desktop")
        with patch("isardvdi_common.helpers.recycle_bin.Helpers.claim_status") as claim:
            with pytest.raises(Error) as exc:
                rb.restore()
        assert exc.value.status_code == 428
        assert status in exc.value.error["description"]
        claim.assert_not_called()

    def test_an_entry_that_moved_after_the_snapshot_is_refused(self):
        """The snapshot says recycled and the row no longer is: only the claim
        can see that, and it must stop the call before any restore work."""
        from isardvdi_common.helpers.recycle_bin import Error

        rb = _bare_entry(status="recycled", id="rb1", owner_id="u1", item_type="user")
        with patch(
            "isardvdi_common.helpers.recycle_bin.Helpers.claim_status",
            return_value=False,
        ) as claim:
            with patch.object(
                type(rb), "check_can_restore", MagicMock()
            ) as can_restore:
                with pytest.raises(Error) as exc:
                    rb.restore()
        assert exc.value.status_code == 428
        can_restore.assert_not_called()
        claim.assert_called_once()
        assert claim.call_args[0][1] == "recycled"
        assert claim.call_args[0][2] == "restored"


class TestClaimStatusIsConditionalOnTheServer:
    def _run(self, replaced):
        from isardvdi_common.helpers import recycle_bin as mod

        conn = MagicMock()
        with patch.object(mod.Helpers, "_rdb_context", MagicMock()):
            with patch.object(mod, "r") as rethink:
                query = rethink.table.return_value.get.return_value.update.return_value
                query.run.return_value = {"replaced": replaced}
                mod.Helpers._rdb_connection = conn
                for name in (
                    "clear_get_item_count_cache",
                    "clear_get_count_cache",
                    "clear_get_user_amount_cache",
                    "clear_get_user_recycle_bin_ids_cache",
                ):
                    setattr(mod.Helpers, name, MagicMock())
                out = mod.Helpers.claim_status("rb1", "recycled", "restored")
                update_kwargs = (
                    rethink.table.return_value.get.return_value.update.call_args
                )
        return out, update_kwargs

    def test_a_write_that_changed_nothing_reports_failure(self):
        out, _ = self._run(replaced=0)
        assert out is False

    def test_a_write_that_landed_reports_success(self):
        out, _ = self._run(replaced=1)
        assert out is True

    def test_the_condition_travels_to_the_server(self):
        _, kwargs = self._run(replaced=1)
        assert kwargs.kwargs.get("return_changes") is True
