#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Consumer-only trim math for the #2084 stopgap ① — MINID trim floor.

No redis / no heavy imports: pure functions the consumer janitor routes through,
unit-testable in isolation. The stream names + ``stream_for_kind`` routing are the
single source of truth in ``isardvdi_common.helpers.task_streams`` (shared with the
storage producer) and re-exported here for the consumer and its tests.
See docs/design/queue-worker-dimensioning.md and the #2084 durability analysis.
"""

from isardvdi_common.helpers.task_streams import (  # noqa: F401  (re-exported)
    PROGRESS_STREAM,
    RESULT_STREAM,
    stream_for_kind,
)


def _id_tuple(entry_id):
    """Parse a redis stream id ``"<ms>-<seq>"`` into an ``(int, int)`` for ordering.

    Redis ids order numerically on ms then seq — NOT lexically ("9-0" < "100-0").
    """
    ms, _, seq = entry_id.partition("-")
    return (int(ms), int(seq or 0))


def min_stream_id(a, b):
    """Return the earlier of two redis stream ids by (ms, seq) ordering."""
    return a if _id_tuple(a) <= _id_tuple(b) else b


def compute_trim_floor(last_delivered_id, min_pending_id):
    """Safe ``MINID`` for ``XTRIM stream:task-results``.

    Only entries that have been BOTH read and ACKed may be trimmed, so the floor
    must never pass:
      * the read frontier (``last-delivered-id``): entries after it are unread and
        trimming them would be exactly the #2084 trim-before-read loss; and
      * the oldest un-ACKed delivered entry (``min`` of the group PEL): that entry
        is still in flight and may need XAUTOCLAIM redelivery.

    Returns the floor id, or ``None`` when trimming is unsafe/unnecessary (nothing
    delivered yet).
    """
    ld = last_delivered_id if last_delivered_id and last_delivered_id != "0-0" else None
    mp = min_pending_id if min_pending_id and min_pending_id != "0-0" else None
    if mp and ld:
        return min_stream_id(mp, ld)
    return mp or ld
