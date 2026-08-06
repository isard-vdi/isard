#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``RecycleBinDeleteQueue.dequeue`` must be crash-safe.

It uses ``set.discard`` (not ``remove``): a re-enqueue/reconcile race can leave
the id absent from the in-memory set, and a ``KeyError`` there would kill the
background worker and silently stall every pending deletion.
"""

import asyncio

import pytest


def _bare_queue():
    from isardvdi_common.helpers.recycle_bin import RecycleBinDeleteQueue

    q = RecycleBinDeleteQueue.__new__(RecycleBinDeleteQueue)
    q.queue = asyncio.Queue()
    q.recycle_bin_ids = set()
    return q


class TestDequeueIsCrashSafe:
    @pytest.mark.asyncio
    async def test_dequeue_missing_id_does_not_raise(self):
        q = _bare_queue()
        # Simulate the race: item in the queue, id NOT tracked in the set.
        await q.queue.put({"recycle_bin_id": "absent", "user_id": "u"})
        item = await q.dequeue()  # set.remove would raise KeyError here
        assert item["recycle_bin_id"] == "absent"

    @pytest.mark.asyncio
    async def test_dequeue_removes_tracked_id(self):
        q = _bare_queue()
        q.recycle_bin_ids.add("rb-1")
        await q.queue.put({"recycle_bin_id": "rb-1", "user_id": "u"})
        item = await q.dequeue()
        assert item["recycle_bin_id"] == "rb-1"
        assert "rb-1" not in q.recycle_bin_ids
