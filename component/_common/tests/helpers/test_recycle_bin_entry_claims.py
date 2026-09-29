# SPDX-License-Identifier: AGPL-3.0-or-later

"""An entry moves only from the statuses the move is meant for."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

MOD = "isardvdi_common.helpers.recycle_bin"


def _bare_queue():
    from isardvdi_common.helpers.recycle_bin import RecycleBinDeleteQueue

    q = RecycleBinDeleteQueue.__new__(RecycleBinDeleteQueue)
    q.queue = asyncio.Queue()
    q.recycle_bin_ids = set()
    return q


def _bare_entry(**attrs):
    from isardvdi_common.helpers.recycle_bin import RecycleBin

    rb = RecycleBin.__new__(RecycleBin)
    defaults = dict(
        id="rb1",
        status="recycled",
        owner_id="u1",
        owner_name="alice",
        agent_id="admin",
        item_type="desktop",
        desktops=[],
        templates=[],
        deployments=[],
        users=[],
        groups=[],
        categories=[],
    )
    for k, v in {**defaults, **attrs}.items():
        setattr(rb, k, v)
    return rb


class TestAPurgeClaimsItsEntry:
    @pytest.mark.asyncio
    async def test_an_entry_that_cannot_be_claimed_is_not_queued(self):
        q = _bare_queue()
        with (
            patch(f"{MOD}.Helpers.claim_for_purge", return_value=False),
            patch(f"{MOD}.Helpers.add_log") as add_log,
            patch(f"{MOD}.Helpers.update_status") as update_status,
        ):
            queued = await q.enqueue({"recycle_bin_id": "rb1", "user_id": "u1"})
        assert queued is False
        assert q.queue.empty()
        add_log.assert_not_called()
        update_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_claimed_entry_is_queued(self):
        q = _bare_queue()
        with (
            patch(f"{MOD}.Helpers.claim_for_purge", return_value=True),
            patch(f"{MOD}.Helpers.add_log"),
        ):
            queued = await q.enqueue({"recycle_bin_id": "rb1", "user_id": "u1"})
        assert queued is True
        assert (await q.queue.get())["recycle_bin_id"] == "rb1"

    @pytest.mark.asyncio
    async def test_a_failed_purge_gives_back_only_its_own_claim(self):
        q = _bare_queue()
        with (
            patch(f"{MOD}.RecycleBin", side_effect=RuntimeError("boom")),
            patch(f"{MOD}.Helpers.claim_status") as claim,
            patch(f"{MOD}.Helpers.update_status") as update_status,
        ):
            await q.perform_operation("rb1", "u1")
        claim.assert_called_once_with("rb1", ["queued", "deleting"], "recycled")
        update_status.assert_not_called()


class TestARestoreClaimsOnlyWhatItCanRestore:
    def test_a_restore_refused_by_its_checks_leaves_the_entry_recycled(self):
        from isardvdi_common.helpers.recycle_bin import Error

        rb = _bare_entry()
        with (
            patch(f"{MOD}.Helpers.claim_status") as claim,
            patch(f"{MOD}.Caches.get_document", return_value=None),
        ):
            with pytest.raises(Error) as exc:
                rb.restore()
        assert exc.value.status_code == 404
        claim.assert_not_called()

    def test_the_owner_is_read_past_the_cache(self):
        from isardvdi_common.helpers.recycle_bin import Error

        rb = _bare_entry()
        with (
            patch(f"{MOD}.Helpers.claim_status", return_value=False),
            patch(f"{MOD}.Caches.get_document", return_value={"id": "u1"}) as get,
            patch.object(type(rb), "check_can_restore", MagicMock()),
        ):
            with pytest.raises(Error):
                rb.restore()
        get.assert_any_call("users", "u1", invalidate=True)

    def test_the_owners_of_the_entry_items_are_read_past_the_cache(self):
        from isardvdi_common.helpers.recycle_bin import Error

        rb = _bare_entry(desktops=[{"user": "u2", "username": "bob"}])
        with patch(f"{MOD}.Caches.get_document", return_value=None) as get:
            with pytest.raises(Error) as exc:
                rb.check_can_restore()
        assert exc.value.status_code == 404
        get.assert_any_call("users", "u2", invalidate=True)
