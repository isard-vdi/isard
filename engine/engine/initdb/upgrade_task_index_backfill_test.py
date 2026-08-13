"""Unit tests for the v205 task-index backfill selection.

The decision of WHAT to backfill lives in ``upgrade_helpers.py`` so it can be
loaded bare (``upgrade.py`` itself cannot: humanfriendly, rethinkdb, config).
The pipelined Redis cascade around it is exercised live against a real stack.

The rule under test is what makes the backfill honest: the row pointer is one
of two sources of truth and the one that lies, so a pointer whose rq job is
gone must NOT become an index member. The index's own invariant is that every
member names a job that exists; seeding it with dead ids would make the reader
prune them on the very next read, and would quietly re-introduce the "row names
a task nobody can load" state the index exists to end.
"""

import os
import runpy
import types

import pytest


def _load_helpers():
    ns = runpy.run_path(
        os.path.join(os.path.dirname(__file__), "upgrade_helpers.py"),
        run_name="_task_index_backfill_under_test",
    )
    return types.SimpleNamespace(**ns)


m = _load_helpers()


class TestBackfillSelection:
    def test_a_row_with_a_live_task_is_backfilled(self):
        rows = [("disk-1", "task-1")]
        assert m.task_index_backfill_entries(rows, {"task-1": 1000.0}) == [
            ("disk-1", "task-1", 1000.0)
        ]

    def test_a_row_that_names_no_task_contributes_nothing(self):
        rows = [("disk-1", None), ("disk-2", ""), ("disk-3", "task-3")]
        assert m.task_index_backfill_entries(rows, {"task-3": 5.0}) == [
            ("disk-3", "task-3", 5.0)
        ]

    def test_a_pointer_whose_job_is_gone_is_skipped(self):
        """The whole point. Nothing ever clears the scalar, so a row can name a
        task whose job expired months ago; that is not history the index can
        hold, and seeding it would be dropped on the next read anyway."""
        rows = [("disk-1", "expired"), ("disk-2", "task-2")]
        assert m.task_index_backfill_entries(rows, {"task-2": 7.0}) == [
            ("disk-2", "task-2", 7.0)
        ]

    def test_the_score_comes_from_the_job_never_from_the_clock(self):
        """Scored with ``now()`` a backfilled entry would outrank a task that
        was really enqueued later — the recycle bin builds tasks that never
        touch the row pointer, so newer index members do exist."""
        rows = [("disk-1", "task-1")]
        entries = m.task_index_backfill_entries(rows, {"task-1": 123.5})
        assert entries[0][2] == 123.5

    def test_input_order_is_preserved(self):
        rows = [("disk-3", "t3"), ("disk-1", "t1"), ("disk-2", "t2")]
        scores = {"t1": 1.0, "t2": 2.0, "t3": 3.0}
        assert [
            owner for owner, _, _ in m.task_index_backfill_entries(rows, scores)
        ] == [
            "disk-3",
            "disk-1",
            "disk-2",
        ]

    def test_an_empty_table_is_no_work(self):
        assert m.task_index_backfill_entries([], {}) == []

    def test_a_row_is_named_once_even_if_it_repeats(self):
        """A re-run over a table read twice must not double-write; ZADD would
        collapse it anyway, but the batch should not carry the duplicate."""
        rows = [("disk-1", "task-1"), ("disk-1", "task-1")]
        assert m.task_index_backfill_entries(rows, {"task-1": 1.0}) == [
            ("disk-1", "task-1", 1.0)
        ]


class _Job:
    def __init__(self, job_id, status):
        self.id = job_id
        self._status = status

    def get_status(self, refresh=False):
        return self._status


def _score(job):
    return 1000.0


class TestOnlyLiveJobsAreCarriedAcross:
    """An upgrade runs with no work in flight, so every pointer it finds names
    a job that already ended — and an rq job survives its execution by its
    result TTL. ``current_task_id`` answers the newest member whose job
    EXISTS, so a finished one seeded here reads as busy and the admission gate
    refuses the row until that TTL runs out. Measured on a live install before this
    filter: three rows seeded, three rows busy, TTL 2.587.534 s.
    """

    @pytest.mark.parametrize("status", ["finished", "failed", "canceled", "stopped"])
    def test_a_terminal_job_is_not_carried_across(self, status):
        scores, terminal = m.live_job_scores([_Job("task-1", status)], _score)
        assert scores == {}
        assert terminal == 1

    def test_a_started_job_is_carried_across(self):
        scores, terminal = m.live_job_scores([_Job("task-1", "started")], _score)
        assert scores == {"task-1": 1000.0}
        assert terminal == 0

    def test_a_queued_job_is_carried_across(self):
        scores, _ = m.live_job_scores([_Job("task-1", "queued")], _score)
        assert scores == {"task-1": 1000.0}

    def test_a_missing_job_is_not_counted_as_terminal(self):
        """``None`` is 'rq dropped it', which the entries helper already skips.
        Counting it as terminal would inflate the number the migration logs."""
        scores, terminal = m.live_job_scores([None], _score)
        assert scores == {}
        assert terminal == 0

    def test_an_unreadable_status_is_carried_across(self):
        """A job whose status cannot be read is not proven terminal, and the
        seed must not silently drop what it could not check."""

        class _Broken(_Job):
            def get_status(self, refresh=False):
                raise RuntimeError("redis blip")

        scores, terminal = m.live_job_scores([_Broken("task-1", None)], _score)
        assert scores == {"task-1": 1000.0}
        assert terminal == 0

    def test_a_terminal_pointer_never_reaches_the_index(self):
        """End to end through both helpers: the row names a finished job, so
        nothing is written for it."""
        scores, _ = m.live_job_scores([_Job("task-1", "finished")], _score)
        assert m.task_index_backfill_entries([("disk-1", "task-1")], scores) == []
