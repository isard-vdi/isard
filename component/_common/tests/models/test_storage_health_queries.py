# SPDX-License-Identifier: AGPL-3.0-or-later

"""The sweep reads its candidates oldest first through indexes, and a check records itself in the row's health."""

from contextlib import nullcontext
from unittest.mock import patch

import pytest
from isardvdi_common.models.storage import Storage
from rethinkdb.ast import RqlQuery


@pytest.fixture
def queries():
    ran = []

    def run(query, *args, **kwargs):
        ran.append(str(query))
        return []

    with (
        patch.object(Storage, "_rdb_context", classmethod(lambda cls: nullcontext())),
        patch.object(type(Storage), "_rdb_connection", None),
        patch.object(RqlQuery, "run", run),
    ):
        yield ran


def test_pending_ids_by_status_walk_the_since_index_in_order(queries):
    Storage.pending_ids("dig_holes", status="ready", limit=5)
    (query,) = queries
    assert "index='status_pending_action_since'" in query
    assert ".between(" in query and ".order_by(index=" in query
    assert "get_all" not in query
    assert ".limit(5)" in query


def test_the_integrity_rotation_reads_the_oldest_check_first(queries):
    Storage.ready_ids_needing_check(1000, 7)
    (query,) = queries
    assert "index='status_integrity_checked'" in query
    assert "1000" in query and ".order_by(index=" in query
    assert "filter" not in query


def test_zeros_due_reads_the_partial_index_least_recently_scanned_first(queries):
    Storage.zeros_due_ids(3)
    (query,) = queries
    assert "index='status_zeros_due'" in query
    assert ".order_by(index=" in query and ".limit(3)" in query


@pytest.mark.parametrize(
    "kwargs, result",
    [({}, "ok"), ({"leaks": 3}, "leaks"), ({"damage_reason": "bad"}, "damaged")],
)
def test_a_check_writes_its_verdict_into_health(queries, kwargs, result):
    Storage.write_check("s1", **kwargs)
    (query,) = queries
    assert "last_checked_at" in query
    assert "integrity" in query and result in query
    assert "checked_at" in query


def test_a_zero_scan_records_the_figure_and_the_size_it_measured(queries):
    Storage.write_zeros("s1", 4096, reclaimable=1024)
    (query,) = queries
    assert "zeros" in query and "1024" in query and "4096" in query
    assert "actual_size_at_scan" in query and "checked_at" in query


def test_a_reflag_keeps_the_original_since_when_the_mark_is_gone(queries):
    Storage.flag_pending("s1", "dig_holes", "dig_holes", since=1234)
    (query,) = queries
    assert "default(1234)" in query
