#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit coverage for the hoisted task-stream routing (#2084 stopgap ①).

These constants + helpers are the single source of truth shared by the storage
producer (docker/storage/task/task.py) and the change-handler consumer
(streams/trim.py); pin their contract so a drift on either side is caught in CI.
"""

from isardvdi_common.helpers.task_streams import (
    PROGRESS_STREAM,
    PROGRESS_STREAM_MAXLEN,
    RESULT_STREAM,
    RESULT_STREAM_HIGH_WATER,
    RESULT_STREAM_MAXLEN_FLOOR,
    maxlen_for_stream,
    result_stream_backpressured,
    stream_for_kind,
)


class _FakeConn:
    """Minimal redis stand-in: XLEN returns a fixed value or raises."""

    def __init__(self, xlen=0, raises=False):
        self._xlen = xlen
        self._raises = raises

    def xlen(self, stream):
        if self._raises:
            raise RuntimeError("redis down")
        return self._xlen


def test_stream_names_are_the_expected_keys():
    assert RESULT_STREAM == "stream:task-results"
    assert PROGRESS_STREAM == "stream:progress"


def test_result_stream_floor_is_high_oom_cap():
    # Large OOM-only floor: the consumer's MINID trim reclaims down to its
    # read+ACK frontier, so this only bites if the consumer is DOWN.
    assert RESULT_STREAM_MAXLEN_FLOOR == 100000
    assert PROGRESS_STREAM_MAXLEN == 10000
    assert RESULT_STREAM_MAXLEN_FLOOR > PROGRESS_STREAM_MAXLEN


def test_progress_routes_to_its_own_stream():
    assert stream_for_kind("progress") == PROGRESS_STREAM


def test_result_and_unknown_kinds_route_to_the_result_stream():
    assert stream_for_kind("result") == RESULT_STREAM
    # Anything that is not "progress" is a result-bearing event and must land on
    # the durable stream — never silently on the disposable progress stream.
    assert stream_for_kind("") == RESULT_STREAM
    assert stream_for_kind("anything-else") == RESULT_STREAM


def test_maxlen_matches_the_stream():
    assert maxlen_for_stream(PROGRESS_STREAM) == PROGRESS_STREAM_MAXLEN
    assert maxlen_for_stream(RESULT_STREAM) == RESULT_STREAM_MAXLEN_FLOOR


def test_high_water_is_below_the_oom_floor():
    # Throttling must start BEFORE the floor would evict a result.
    assert RESULT_STREAM_HIGH_WATER < RESULT_STREAM_MAXLEN_FLOOR


def test_backpressure_true_at_or_above_high_water():
    assert result_stream_backpressured(_FakeConn(xlen=RESULT_STREAM_HIGH_WATER)) is True
    assert (
        result_stream_backpressured(_FakeConn(xlen=RESULT_STREAM_HIGH_WATER + 1))
        is True
    )


def test_backpressure_false_below_high_water():
    assert result_stream_backpressured(_FakeConn(xlen=0)) is False
    assert (
        result_stream_backpressured(_FakeConn(xlen=RESULT_STREAM_HIGH_WATER - 1))
        is False
    )


def test_backpressure_false_on_redis_error():
    # A broken check must never block admission.
    assert result_stream_backpressured(_FakeConn(raises=True)) is False
