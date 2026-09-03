# SPDX-License-Identifier: AGPL-3.0-or-later

"""Recovery has to terminate: page the whole pending list, and give up on an
entry whose delivery count cannot be read.

Both defects strand entries in the PEL, and a stranded entry pins the MINID
trim floor of the result stream as well as never being settled.
"""

from unittest.mock import AsyncMock, patch

import pytest


class _FakeRedis:
    """Enough of the stream API for the reclaim pass, answering honestly.

    ``pages`` maps the cursor XAUTOCLAIM is called with to the reply it gets,
    so a pass that ignores the returned cursor sees only the first page.
    """

    def __init__(self, pages, pending=None, pending_error=None):
        self.pages = pages
        self.pending = pending or {}
        self.pending_error = pending_error
        self.starts = []
        self.acked = []
        self.dead = []

    async def xautoclaim(
        self,
        name,
        groupname,
        consumername,
        min_idle_time=0,
        start_id="0-0",
        count=None,
        justid=False,
    ):
        self.starts.append(start_id)
        return self.pages.get(start_id, ["0-0", [], []])

    async def xpending_range(self, name, groupname, min=None, max=None, count=None):
        if self.pending_error is not None:
            raise self.pending_error
        entry = self.pending.get(min)
        return [entry] if entry else []

    async def xack(self, name, groupname, entry_id):
        self.acked.append(entry_id)

    async def xadd(self, name, fields, maxlen=None, approximate=None):
        self.dead.append((name, fields))


@pytest.fixture(autouse=True)
def clear_reclaim_state():
    from isardvdi_change_handler.streams import task_results_consumer as c

    # getattr with a default so this file also runs against a build that has
    # no such state, which is how it is checked against unpatched main.
    getattr(c, "_unreadable_reclaims", {}).clear()
    yield
    getattr(c, "_unreadable_reclaims", {}).clear()


def _entries(prefix, count):
    return [
        (f"{prefix}{index}-0", {"kind": "result", "task_id": f"task-{prefix}{index}"})
        for index in range(count)
    ]


@pytest.mark.asyncio
async def test_reclaim_pages_through_the_whole_pending_list():
    from isardvdi_change_handler.streams import task_results_consumer as c

    first, second = _entries("a", 32), _entries("b", 8)
    redis = _FakeRedis(
        {"0-0": ["500-0", first, []], "500-0": ["0-0", second, []]},
    )
    processed = AsyncMock(return_value=True)
    with patch.object(c, "_process_entry", new=processed):
        await c._reclaim_pending(redis, AsyncMock(), "consumer-1")

    assert processed.await_count == len(first) + len(second), (
        f"the pass settled {processed.await_count} of "
        f"{len(first) + len(second)} pending entries and then stopped; "
        f"XAUTOCLAIM was resumed from {redis.starts}"
    )


@pytest.mark.asyncio
async def test_an_entry_whose_delivery_count_is_unreadable_is_given_up_on():
    from isardvdi_change_handler.streams import task_results_consumer as c

    stuck = _entries("z", 1)
    redis = _FakeRedis(
        {"0-0": ["0-0", stuck, []]},
        pending_error=ConnectionError("PEL unreadable"),
    )
    passes = 20
    with patch.object(c, "_process_entry", new=AsyncMock(return_value=False)):
        for _ in range(passes):
            await c._reclaim_pending(redis, AsyncMock(), "consumer-1")

    assert redis.dead, (
        f"after {passes} reclaim passes the entry whose XPENDING could not be "
        "read has never been dead-lettered, so it is retried for ever and "
        "holds the trim floor down"
    )
    assert redis.acked, "a dead-lettered entry must also leave the pending list"


@pytest.mark.asyncio
async def test_a_readable_delivery_count_still_bounds_retries():
    from isardvdi_change_handler.streams import task_results_consumer as c

    stuck = _entries("y", 1)
    entry_id = stuck[0][0]
    redis = _FakeRedis(
        {"0-0": ["0-0", stuck, []]},
        pending={entry_id: {"times_delivered": c.MAX_DELIVERIES + 1}},
    )
    with patch.object(c, "_process_entry", new=AsyncMock(return_value=False)):
        await c._reclaim_pending(redis, AsyncMock(), "consumer-1")

    assert [name for name, _fields in redis.dead] == [c.DEAD_STREAM]
    assert redis.acked == [entry_id]


@pytest.mark.asyncio
async def test_the_progress_drain_pages_through_its_pending_list_too():
    from isardvdi_change_handler.streams import task_results_consumer as c

    first, second = _entries("p", 32), _entries("q", 5)
    redis = _FakeRedis({"0-0": ["900-0", first, []], "900-0": ["0-0", second, []]})

    dropped = await c._drain_progress_pel(redis, "consumer-1")

    assert dropped == len(first) + len(second), (
        f"the drain dropped {dropped} of {len(first) + len(second)} stale "
        f"progress entries and then stopped; XAUTOCLAIM was resumed from "
        f"{redis.starts}"
    )
