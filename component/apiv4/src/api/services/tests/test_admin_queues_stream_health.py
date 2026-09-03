#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Josep Maria Viñolas Auquer
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The governor gauge reports the task streams' own backlog.

Nothing else can. A task whose worker has finished has already left its rq
queue, so a chain waiting on the change-handler to run its finalize handlers
adds to no backlog, no oldest-queued age and no alert. Measured on a clean
install under a burst: the consumer group reached a lag of 892 while the
deepest rq queue held 100 and not one alert fired — the operator sees the
finished counter climb and the rows never settle, with nothing naming the
cause.
"""

from unittest.mock import MagicMock

from api.services.admin.queues import _stream_health


def _conn(lengths=None, groups=None):
    """A redis stand-in answering only what ``_stream_health`` reads."""
    lengths = lengths or {}
    groups = groups or {}
    conn = MagicMock(name="redis")
    conn.xlen.side_effect = lambda stream: lengths[stream]
    conn.xinfo_groups.side_effect = lambda stream: groups[stream]
    return conn


RESULTS = "stream:task-results"
PROGRESS = "stream:progress"
DEAD = "stream:task-results:dead"


def test_the_backlog_no_queue_gauge_can_show():
    health = _stream_health(
        _conn(
            lengths={RESULTS: 977, PROGRESS: 12, DEAD: 0},
            groups={
                RESULTS: [
                    {
                        "name": "change-handler",
                        "lag": 892,
                        "pending": 26,
                        "consumers": 1,
                    }
                ],
                PROGRESS: [],
            },
        )
    )

    assert health["up"] is True
    assert health["results_length"] == 977
    assert health["groups"] == [
        {
            "stream": RESULTS,
            "group": "change-handler",
            "lag": 892,
            "pending": 26,
            "consumers": 1,
        }
    ]


def test_a_group_name_survives_a_bytes_client():
    """redis-py hands back bytes or str depending on how it was constructed;
    a group whose name arrives as bytes must still be labelled."""
    health = _stream_health(
        _conn(
            lengths={RESULTS: 1, PROGRESS: 0, DEAD: 0},
            groups={RESULTS: [{"name": b"change-handler"}], PROGRESS: []},
        )
    )

    assert health["groups"][0]["group"] == "change-handler"


def test_an_uncomputable_lag_keeps_the_rest_of_the_row():
    """Redis reports ``lag`` as None once entries have been trimmed from under
    a group. Dropping the row would hide the pending count too — the operator
    loses more than the one number redis could not give."""
    health = _stream_health(
        _conn(
            lengths={RESULTS: 5, PROGRESS: 0, DEAD: 0},
            groups={
                RESULTS: [{"name": "change-handler", "lag": None, "pending": 3}],
                PROGRESS: [],
            },
        )
    )

    assert health["groups"][0]["lag"] == 0
    assert health["groups"][0]["pending"] == 3


def test_a_stream_nobody_has_written_to_is_a_zero_not_a_failure():
    """On a fresh deployment the dead-letter stream does not exist. That is the
    normal state and must not cost the operator the two numbers that do."""
    conn = MagicMock(name="redis")
    conn.xlen.side_effect = lambda stream: (
        7 if stream == RESULTS else _raise(Exception("no such key"))
    )
    conn.xinfo_groups.return_value = []

    health = _stream_health(conn)

    assert health["up"] is True
    assert health["results_length"] == 7
    assert health["dead_length"] == 0


def test_a_dead_redis_reports_down_instead_of_raising():
    """This block rides on a document whose whole contract is to degrade rather
    than raise: a polled 500 ejects the operator mid-incident."""
    conn = MagicMock(name="redis")
    conn.xlen.side_effect = Exception("redis is unreachable")
    conn.xinfo_groups.side_effect = Exception("redis is unreachable")

    health = _stream_health(conn)

    assert health["up"] is True  # the reads failed individually, not the block
    assert health["groups"] == []


def test_the_dead_letter_count_reaches_the_operator():
    """Nothing consumes the dead-letter stream, so its depth is the only trace
    of an entry that failed every redelivery."""
    health = _stream_health(
        _conn(
            lengths={RESULTS: 0, PROGRESS: 0, DEAD: 4},
            groups={RESULTS: [], PROGRESS: []},
        )
    )

    assert health["dead_length"] == 4


def _raise(exc):
    raise exc
