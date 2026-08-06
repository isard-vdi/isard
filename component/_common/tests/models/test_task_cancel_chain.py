# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin-down tests for the chain-closure semantics of ``Task.cancel()``.

Cancelling any member of a chain settles the WHOLE chain as ``CANCELED``
and promotes nothing. The invariant these tests defend is that a cancel
can never leave a job QUEUED on the consumerless ``core`` queue: such a
job is counted as active by ``Task.pending``, which makes
``Storage.create_task`` reject every later operation on that storage with
``storage_pending_task`` forever.

The Task class is redis-backed, so — like the sibling cancel suite — we
drive ``cancel()`` on a bare instance with the job graph faked out.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from isardvdi_common.models.task import _ENDED_AT_STAMP, Task
from rq.exceptions import InvalidJobOperation, NoSuchJobError
from rq.job import JobStatus


def _job(job_id, *, status=JobStatus.QUEUED, dependencies=(), dependents=()):
    """A fake RQ ``Job`` exposing only what the closure walk reads."""
    job = MagicMock()
    job.id = job_id
    job.meta = {
        "dependency_ids": list(dependencies),
        "dependent_ids": list(dependents),
    }
    job.get_status.return_value = status
    return job


def _task_for(job, graph):
    """Bare ``Task`` over ``job``, with ``Job.fetch`` resolving ``graph``."""
    task = Task.__new__(Task)
    task.job = job
    return task


def _patch_graph(graph):
    """Patch the module's ``Job.fetch`` to resolve ids from ``graph``."""

    def _fetch(job_id, connection=None):
        try:
            return graph[job_id]
        except KeyError:
            raise NoSuchJobError(job_id)

    return patch("isardvdi_common.models.task.Job.fetch", side_effect=_fetch)


class TestCancelNeverPromotes:
    """The F1 invariant: no cancel path may enqueue dependents."""

    def test_single_job_cancel_does_not_enqueue_dependents(self):
        root = _job("root")
        graph = {"root": root}
        task = _task_for(root, graph)

        with _patch_graph(graph), patch.object(Task, "_redis", MagicMock()), patch(
            "isardvdi_common.helpers.task_cancel.request_task_cancel"
        ):
            task.cancel()

        root.cancel.assert_called_once_with(enqueue_dependents=False)

    def test_core_dependent_is_canceled_not_promoted(self):
        """A ``core`` finalize dependent must be CANCELED, never queued.

        The shape seen in production: a storage root with a ``core``
        ``storage_update`` dependent. Under the old behaviour rq moved the
        dependent DEFERRED -> QUEUED onto the consumerless ``core`` queue.
        """
        root = _job("root", dependents=["core-dep"])
        core_dep = _job("core-dep", status=JobStatus.DEFERRED, dependencies=["root"])
        graph = {"root": root, "core-dep": core_dep}
        task = _task_for(root, graph)

        with _patch_graph(graph), patch.object(Task, "_redis", MagicMock()), patch(
            "isardvdi_common.helpers.task_cancel.request_task_cancel"
        ):
            task.cancel()

        core_dep.cancel.assert_called_once_with(enqueue_dependents=False)
        root.cancel.assert_called_once_with(enqueue_dependents=False)


class TestCancelWalksTheWholeClosure:
    def test_cancel_from_middle_settles_parents_and_children(self):
        """Cancelling any member settles the whole weakly-connected chain."""
        root = _job("root", dependents=["mid"])
        mid = _job("mid", dependencies=["root"], dependents=["leaf"])
        leaf = _job("leaf", status=JobStatus.DEFERRED, dependencies=["mid"])
        graph = {"root": root, "mid": mid, "leaf": leaf}
        task = _task_for(mid, graph)

        with _patch_graph(graph), patch.object(Task, "_redis", MagicMock()), patch(
            "isardvdi_common.helpers.task_cancel.request_task_cancel"
        ):
            task.cancel()

        for job in (root, mid, leaf):
            job.cancel.assert_called_once_with(enqueue_dependents=False)

    def test_dependents_are_canceled_before_their_dependencies(self):
        """Leaves-first: a dependent must be settled before its dependency.

        Otherwise rq could still observe a dependency reaching a terminal
        state while the dependent is not yet canceled.
        """
        order = []
        root = _job("root", dependents=["leaf"])
        leaf = _job("leaf", status=JobStatus.DEFERRED, dependencies=["root"])
        root.cancel.side_effect = lambda **_: order.append("root")
        leaf.cancel.side_effect = lambda **_: order.append("leaf")
        graph = {"root": root, "leaf": leaf}
        task = _task_for(root, graph)

        with _patch_graph(graph), patch.object(Task, "_redis", MagicMock()), patch(
            "isardvdi_common.helpers.task_cancel.request_task_cancel"
        ):
            task.cancel()

        assert order == ["leaf", "root"]

    def test_vanished_member_does_not_break_the_sweep(self):
        """A dangling id in meta must not abort the cancel."""
        root = _job("root", dependents=["gone", "leaf"])
        leaf = _job("leaf", status=JobStatus.DEFERRED, dependencies=["root"])
        graph = {"root": root, "leaf": leaf}  # "gone" deliberately absent
        task = _task_for(root, graph)

        with _patch_graph(graph), patch.object(Task, "_redis", MagicMock()), patch(
            "isardvdi_common.helpers.task_cancel.request_task_cancel"
        ):
            task.cancel()

        leaf.cancel.assert_called_once_with(enqueue_dependents=False)
        root.cancel.assert_called_once_with(enqueue_dependents=False)


class TestTerminalMembersAreLeftAlone:
    def test_finished_dependency_is_not_recanceled(self):
        """A finished step keeps its history — cancelling a later step must
        not rewrite it to CANCELED."""
        root = _job("root", status=JobStatus.FINISHED, dependents=["leaf"])
        leaf = _job("leaf", status=JobStatus.DEFERRED, dependencies=["root"])
        graph = {"root": root, "leaf": leaf}
        task = _task_for(leaf, graph)

        with _patch_graph(graph), patch.object(Task, "_redis", MagicMock()), patch(
            "isardvdi_common.helpers.task_cancel.request_task_cancel"
        ):
            task.cancel()

        root.cancel.assert_not_called()
        leaf.cancel.assert_called_once_with(enqueue_dependents=False)

    def test_double_cancel_does_not_raise(self):
        """Re-cancelling an already-canceled chain is a no-op, not a 500.

        ``admin_cancel_task`` has no status gate, so an operator clearing a
        wedged task twice used to get ``InvalidJobOperation`` straight out
        of rq as a 500.
        """
        root = _job("root", status=JobStatus.CANCELED)
        root.cancel.side_effect = InvalidJobOperation("already canceled")
        graph = {"root": root}
        task = _task_for(root, graph)

        with _patch_graph(graph), patch.object(Task, "_redis", MagicMock()), patch(
            "isardvdi_common.helpers.task_cancel.request_task_cancel"
        ):
            task.cancel()  # must not raise

    def test_cancel_race_swallows_invalid_job_operation(self):
        """A concurrent cancel between our status read and our cancel call
        must not surface as an error."""
        root = _job("root", status=JobStatus.QUEUED)
        root.cancel.side_effect = InvalidJobOperation("raced")
        graph = {"root": root}
        task = _task_for(root, graph)

        with _patch_graph(graph), patch.object(Task, "_redis", MagicMock()), patch(
            "isardvdi_common.helpers.task_cancel.request_task_cancel"
        ):
            task.cancel()  # must not raise


class TestCancelSettlesAndAnnounces:
    def test_ended_at_is_stamped_on_every_canceled_member(self):
        """rq's cancel never writes ``ended_at``; without it the reconcile
        age gate can never settle the chain, so it lingers forever."""
        root = _job("root", dependents=["leaf"])
        leaf = _job("leaf", status=JobStatus.DEFERRED, dependencies=["root"])
        graph = {"root": root, "leaf": leaf}
        task = _task_for(root, graph)
        fake_redis = MagicMock()

        with _patch_graph(graph), patch.object(Task, "_redis", fake_redis), patch(
            "isardvdi_common.helpers.task_cancel.request_task_cancel"
        ):
            task.cancel()

        # Select by SCRIPT, not by "everything that reached eval": the cancel
        # path stamps an expiry through the same connection, and asserting over
        # every eval call would make this test fail for a change it does not
        # describe.
        stamped = {
            call.args[2].decode() if isinstance(call.args[2], bytes) else call.args[2]
            for call in fake_redis.eval.call_args_list
            if len(call.args) > 2 and call.args[0] is _ENDED_AT_STAMP
        }
        assert stamped == {"rq:job:root", "rq:job:leaf"}

    def test_canceled_event_published_for_the_chain_root(self):
        """The change-handler is the only executor of finalize handlers, so
        a cancel must announce itself on the result stream for the canceled
        finalize to run."""
        root = _job("root", dependents=["leaf"])
        root.func_name = "task.resize"
        root.origin = "storage.pool.maintenance"
        leaf = _job("leaf", status=JobStatus.DEFERRED, dependencies=["root"])
        graph = {"root": root, "leaf": leaf}
        task = _task_for(root, graph)

        with _patch_graph(graph), patch.object(Task, "_redis", MagicMock()), patch(
            "isardvdi_common.helpers.task_cancel.request_task_cancel"
        ), patch("isardvdi_common.models.task.publish_canceled_event") as publish:
            task.cancel()

        assert publish.call_count == 1
        assert publish.call_args.kwargs["task_id"] == "root"

    def test_event_publish_failure_does_not_break_cancel(self):
        """A stream blip must never fail a cancel — reconcile is the
        backstop."""
        root = _job("root")
        graph = {"root": root}
        task = _task_for(root, graph)

        with _patch_graph(graph), patch.object(Task, "_redis", MagicMock()), patch(
            "isardvdi_common.helpers.task_cancel.request_task_cancel"
        ), patch(
            "isardvdi_common.models.task.publish_canceled_event",
            side_effect=RuntimeError("stream down"),
        ):
            task.cancel()  # must not raise

        root.cancel.assert_called_once_with(enqueue_dependents=False)


class TestEndedAtStampSemantics:
    """The stamp runs as a Lua script, so a mocked connection cannot tell us
    whether it actually writes. These pin the semantics that matter against a
    real redis when one is available (``ISARD_TEST_REDIS``), which is how the
    empty-field trap below was found in the first place.
    """

    @staticmethod
    def _redis_or_skip():
        """One criterion for "is there a real Redis here", shared with every
        other suite that needs one: an explicit ``ISARD_TEST_REDIS`` if set,
        otherwise the server the rest of the stack is configured against — and
        skip when it cannot be reached.

        Never the rq db: these write fixed ``rq:job:test-stamp-*`` keys, and a
        unit test has no business writing into the db real jobs live in. The
        connect timeout keeps "there is no Redis here" from becoming a hung job
        on an unresolvable host.
        """
        import os

        import pytest
        import redis as redis_lib

        url = os.environ.get("ISARD_TEST_REDIS")
        if url:
            connection = redis_lib.from_url(
                url, socket_connect_timeout=5, socket_timeout=5
            )
        else:
            connection = redis_lib.Redis(
                host=os.environ.get("REDIS_HOST") or "isard-redis",
                port=int(os.environ.get("REDIS_PORT") or 6379),
                password=os.environ.get("REDIS_PASSWORD", ""),
                db=int(os.environ.get("TASK_CHAIN_TEST_REDIS_DB", "9")),
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        assert (
            connection.get_connection_kwargs().get("db") != 0
        ), "refusing to run against the rq db"
        try:
            connection.ping()
        except Exception as error:
            from isardvdi_common.redis_test_gate import redis_required

            redis_required(f"no Redis for the real-redis stamp tests: {error}")
        return connection

    def test_stamps_when_the_field_is_empty(self):
        """RQ serialises an unset ``ended_at`` as an EMPTY field, not a missing
        one — a plain ``HSETNX`` writes nothing and the chain can never age."""
        from isardvdi_common.models.task import _stamp_ended_at

        conn = self._redis_or_skip()
        key = "rq:job:test-stamp-empty"
        conn.delete(key)
        conn.hset(key, mapping={"status": "canceled", "ended_at": ""})

        _stamp_ended_at(conn, "test-stamp-empty")

        assert conn.hget(key, "ended_at") not in (b"", None)
        conn.delete(key)

    def test_does_not_overwrite_a_real_timestamp(self):
        from isardvdi_common.models.task import _stamp_ended_at

        conn = self._redis_or_skip()
        key = "rq:job:test-stamp-keep"
        conn.delete(key)
        conn.hset(
            key, mapping={"status": "finished", "ended_at": "2020-01-01T00:00:00Z"}
        )

        _stamp_ended_at(conn, "test-stamp-keep")

        assert conn.hget(key, "ended_at") == b"2020-01-01T00:00:00Z"
        conn.delete(key)

    def test_does_not_resurrect_a_deleted_job(self):
        """A concurrently-deleted job must not come back as a status-only ghost
        hash — those poison every chain walk that meets them."""
        from isardvdi_common.models.task import _stamp_ended_at

        conn = self._redis_or_skip()
        key = "rq:job:test-stamp-gone"
        conn.delete(key)

        _stamp_ended_at(conn, "test-stamp-gone")

        assert conn.exists(key) == 0
