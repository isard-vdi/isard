#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared task-stream names + routing for the #2084 stopgap ① (progress split).

Single source of truth for the storage-worker producer
(``docker/storage/task/task.py``) and the change-handler consumer
(``streams/trim.py`` / ``streams/task_results_consumer.py``), which previously
duplicated these constants because the storage image doesn't ship the
change-handler package. No redis / no heavy imports: pure names + functions so
both sides — and their unit tests — can import them cheaply.

See docs/design/queue-worker-dimensioning.md and the #2084 durability analysis.
"""

# Result completions MUST NOT be trimmed before the consumer has read them.
RESULT_STREAM = "stream:task-results"
# Progress heartbeats are disposable and high-volume — their own stream so they
# can never evict an unread result from a shared budget.
PROGRESS_STREAM = "stream:progress"

# Hard OOM floor for the result stream. The change-handler consumer drives a MINID
# trim down to its read+ACK frontier (stopgap ①), so this large cap only
# bites if the consumer is DOWN — bounded, recoverable loss instead of an unbounded
# stream. Replaces the old tight ``MAXLEN=10000 approximate`` that discarded UNREAD
# ``kind=result`` entries under a burst.
RESULT_STREAM_MAXLEN_FLOOR = 100000
# Progress is disposable + high-volume: tight approximate cap so it can never evict
# a result.
PROGRESS_STREAM_MAXLEN = 10000

# Admission high-water for enqueue backpressure (stopgap ①). When the result stream
# holds this many un-trimmed entries the change-handler consumer is far behind, so
# new result-producing work is throttled at enqueue. Below the 100k OOM floor so
# throttling kicks in BEFORE the floor would evict a result.
RESULT_STREAM_HIGH_WATER = 90000


def stream_for_kind(kind):
    """Route a task event to its stream by ``kind`` (the progress split, #2084 ①)."""
    return PROGRESS_STREAM if kind == "progress" else RESULT_STREAM


def maxlen_for_stream(stream):
    """The XADD ``maxlen`` cap for a given stream name."""
    return (
        PROGRESS_STREAM_MAXLEN
        if stream == PROGRESS_STREAM
        else RESULT_STREAM_MAXLEN_FLOOR
    )


def result_stream_backpressured(connection, high_water=RESULT_STREAM_HIGH_WATER):
    """True when the result stream is near its floor (consumer far behind).

    Drives the enqueue admission throttle (stopgap ①). Takes the redis connection as
    an argument so this module stays dependency-free (no redis import). Best-effort:
    any redis error returns ``False`` — a broken check must never block task
    admission.
    """
    try:
        return connection.xlen(RESULT_STREAM) >= high_water
    except Exception:
        return False
