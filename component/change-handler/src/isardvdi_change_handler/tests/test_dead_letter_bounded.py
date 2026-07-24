# SPDX-License-Identifier: AGPL-3.0-or-later

"""The dead-letter stream must be bounded.

Nothing consumes it, so an uncapped XADD grows for ever on any install that
ever dead-letters. It is a forensic record, not a queue.
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_dead_letter_xadd_is_capped():
    from isardvdi_change_handler.streams import task_results_consumer as c

    redis = AsyncMock()
    with (
        patch.object(
            c, "_delivery_count", new=AsyncMock(return_value=c.MAX_DELIVERIES + 1)
        ),
        patch.object(c, "_ack", new=AsyncMock()),
    ):
        await c._reclaim_pending(redis, AsyncMock(), "consumer-1")

    dead_calls = [
        call
        for call in redis.xadd.call_args_list
        if call.args and call.args[0] == c.DEAD_STREAM
    ]
    for call in dead_calls:
        assert call.kwargs.get("maxlen") == c.DEAD_STREAM_MAXLEN
        assert call.kwargs.get("approximate") is True


def test_the_cap_is_declared():
    from isardvdi_change_handler.streams import task_results_consumer as c

    assert isinstance(c.DEAD_STREAM_MAXLEN, int)
    assert c.DEAD_STREAM_MAXLEN > 0
