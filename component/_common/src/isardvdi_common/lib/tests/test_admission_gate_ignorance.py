# SPDX-License-Identifier: AGPL-3.0-or-later

"""What the admission gate does when it cannot read redis at all.

Two halves of the system used to answer the same fact — redis unreachable — in
opposite ways. Observability was honest: the governor degrades to
``redis: {up: false}`` and the admin panel paints a red banner. Admission lied:
every read error fell through to "ok", so the gate yielded and the user was told
nothing. A blip therefore admitted work the fleet might never drain, and two
chains could be created over the same row.

The distinction that matters, and these are NOT the same fact:

* a rolling worker restart is redis ANSWERING that a lane momentarily has no
  consumer. That is knowledge, and it must keep admitting — the fleet-gap grace;
* redis unreachable is the ABSENCE of knowledge. Admitting on it is the guard
  permitting exactly what it exists to prevent.

For the user the second is equivalent to a lane with no consumers, so it takes
the 429 that already exists rather than a new mechanism.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from isardvdi_common.lib import queue_coverage as qc  # noqa: E402


class _DeadRedis:
    """Every call raises, the way a real client does when redis is gone."""

    def __getattr__(self, name):
        def _boom(*args, **kwargs):
            raise ConnectionError("redis is unreachable")

        return _boom


def test_an_unreadable_index_does_not_admit():
    """The whole point: ignorance must not read as "the lane is fine"."""
    decision, ctx = qc.lane_shed_decision(_DeadRedis(), "storage.p1.interactive")

    assert decision == "reject"
    assert ctx["reason"] == "coverage_unreadable"
    assert ctx["pool"] == "p1"
    assert ctx["tier"] == "interactive"


def test_the_caller_gets_the_same_429_a_consumerless_lane_gives():
    """No new mechanism and nothing for the frontend to learn: the user sees
    what they already see when a lane has no consumer."""
    with pytest.raises(Exception) as excinfo:
        qc.check_shed(_DeadRedis(), "storage.p1.interactive")

    assert getattr(excinfo.value, "status_code", None) == 429
    # ``error`` dict, not an attribute: outside apiv4 the factory resolves to
    # ErrorBase, and that is where both carry the description code.
    assert getattr(excinfo.value, "error", {}).get("description_code") == (
        "storage_no_consumer_retry_later"
    )


def test_the_mandatory_producer_gate_also_refuses():
    """``check_no_consumer`` runs on every producer and only raised for
    ``no_consumer``. An unreadable index has to reach it too, or the gate that
    is mandatory everywhere is the one that keeps failing open."""
    with pytest.raises(Exception) as excinfo:
        qc.check_no_consumer(_DeadRedis(), "storage.p1.interactive")

    assert getattr(excinfo.value, "status_code", None) == 429


def test_the_429_survives_the_counter_it_cannot_write():
    """``_raise_lane_429`` records the shed before raising, and here that write
    fails too. The rejection must still reach the caller: a guard that turns
    into a 500 because it could not count itself has not refused anything."""
    with pytest.raises(Exception) as excinfo:
        qc.check_shed(_DeadRedis(), "storage.p1.interactive")

    assert getattr(excinfo.value, "status_code", None) == 429


def test_a_non_storage_queue_is_still_none_of_this():
    """The gate only speaks about storage lanes; anything else is not its
    business even when redis is dead."""
    decision, ctx = qc.lane_shed_decision(_DeadRedis(), "notifier")

    assert decision == "ok"
    assert ctx["reason"] == "non_storage_queue"
