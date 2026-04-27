# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``isardvdi_common.helpers.task_cancel``.

Covers the two surfaces of the cooperative-cancellation primitive:

* :func:`request_task_cancel` — one-shot publish on
  ``task:cancel:<id>``. We pin the channel name (the long-running
  task body subscribes by exact name) and that the redis ``publish``
  return value (subscriber count) is propagated back to the caller.

* :class:`TaskCancelWatcher` — context manager that flips
  ``cancelled`` when a message arrives. We pin: the ``initial_check``
  fast-path (no thread spawned, no subscribe call), the subscribe-
  channel name, and the cancellation transition when the daemon
  thread sees a message. The thread itself is exercised against a
  fake pubsub so the test does not depend on a live redis.

The actual blocking ``pubsub.get_message`` loop is collapsed into a
single ``side_effect`` queue that returns ``None`` (timeout) → the
cancel message → ``None`` (drained) so the thread exits naturally on
``__exit__``.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

from isardvdi_common.helpers import task_cancel
from isardvdi_common.helpers.task_cancel import (
    TaskCancelWatcher,
    _channel,
    request_task_cancel,
)


class TestChannelName:
    """Channel format is part of the wire contract — apiv4 publishes,
    the storage worker subscribes, both encode the same string."""

    def test_channel_format(self):
        assert _channel("abc") == "task:cancel:abc"

    def test_channel_with_uuid_shape(self):
        # RQ ids are uuid-like; we don't sanitize, just concatenate.
        assert (
            _channel("c2d4e8a0-1111-2222-3333-444455556666")
            == "task:cancel:c2d4e8a0-1111-2222-3333-444455556666"
        )


class TestRequestTaskCancel:
    @patch.object(task_cancel.RedisBase, "_redis")
    def test_publishes_on_correct_channel_with_cancel_payload(self, mock_redis):
        mock_redis.publish.return_value = 0
        request_task_cancel("task-xyz")
        mock_redis.publish.assert_called_once_with("task:cancel:task-xyz", b"cancel")

    @patch.object(task_cancel.RedisBase, "_redis")
    def test_returns_subscriber_count_from_publish(self, mock_redis):
        mock_redis.publish.return_value = 3
        assert request_task_cancel("t1") == 3

    @patch.object(task_cancel.RedisBase, "_redis")
    def test_zero_subscribers_is_returned_as_zero(self, mock_redis):
        # Common case: cancel arrives before the worker subscribed (or
        # after it finished). Caller must be able to distinguish.
        mock_redis.publish.return_value = 0
        assert request_task_cancel("t1") == 0


def _fake_redis_with_kwargs():
    """A MagicMock whose ``connection_pool.connection_kwargs`` returns
    plausible values, so ``TaskCancelWatcher.__init__`` can build a
    fresh ``Redis(...)`` from it without touching the network."""
    fake = MagicMock()
    fake.connection_pool.connection_kwargs = {
        "host": "isard-redis",
        "port": 6379,
        "password": "",
        "db": 1,
    }
    return fake


class TestTaskCancelWatcherInitialCheck:
    """If the persistent flag is already set when the watcher enters,
    we must short-circuit: no subscribe, no thread, ``cancelled`` true.
    This closes the ``request_task_cancel`` → worker-not-yet-subscribed
    race documented in the module."""

    @patch.object(task_cancel.RedisBase, "_redis", _fake_redis_with_kwargs())
    def test_true_initial_check_skips_subscribe_and_thread(self):
        fake_conn = MagicMock()
        with TaskCancelWatcher(
            "t1", initial_check=lambda: True, connection=fake_conn
        ) as watcher:
            assert watcher.cancelled is True
            # No pubsub built, no subscribe issued, no daemon spawned.
            fake_conn.pubsub.assert_not_called()
            assert watcher._thread is None

    @patch.object(task_cancel.RedisBase, "_redis", _fake_redis_with_kwargs())
    def test_false_initial_check_proceeds_to_subscribe(self):
        fake_conn = MagicMock()
        fake_pubsub = MagicMock()
        # First .get_message returns None each time so the thread idles.
        fake_pubsub.get_message.return_value = None
        fake_conn.pubsub.return_value = fake_pubsub

        with TaskCancelWatcher(
            "t1", initial_check=lambda: False, connection=fake_conn
        ) as watcher:
            fake_pubsub.subscribe.assert_called_once_with("task:cancel:t1")
            assert watcher.cancelled is False
            assert watcher._thread is not None

    @patch.object(task_cancel.RedisBase, "_redis", _fake_redis_with_kwargs())
    def test_initial_check_exception_is_swallowed_and_we_subscribe(self):
        """A bad initial_check (e.g. transient DB read failure) must
        not abort the watcher — we still want to listen for live
        cancel signals."""

        def bad_check():
            raise RuntimeError("boom")

        fake_conn = MagicMock()
        fake_pubsub = MagicMock()
        fake_pubsub.get_message.return_value = None
        fake_conn.pubsub.return_value = fake_pubsub

        with TaskCancelWatcher(
            "t1", initial_check=bad_check, connection=fake_conn
        ) as watcher:
            fake_pubsub.subscribe.assert_called_once_with("task:cancel:t1")
            assert watcher.cancelled is False


class TestTaskCancelWatcherSignalDelivery:
    @patch.object(task_cancel.RedisBase, "_redis", _fake_redis_with_kwargs())
    def test_message_arrival_sets_cancelled(self):
        """A non-None message returned by ``get_message`` is the cancel
        signal (the watcher uses ``ignore_subscribe_messages=True`` so
        the subscribe ack is filtered out)."""
        fake_conn = MagicMock()
        fake_pubsub = MagicMock()

        # Sequence: a few timeouts, then one cancel, then drained.
        # The watcher returns from _run on the first non-None msg.
        messages = [None, None, {"type": "message", "data": b"cancel"}, None]
        fake_pubsub.get_message.side_effect = messages
        fake_conn.pubsub.return_value = fake_pubsub

        with TaskCancelWatcher("t1", connection=fake_conn) as watcher:
            # The daemon thread iterates `get_message`. Wait for the
            # cancellation event with a generous timeout — the loop is
            # CPU-only against a mock, so it converges almost instantly.
            assert watcher.wait(timeout=2.0)
            assert watcher.cancelled is True

    @patch.object(task_cancel.RedisBase, "_redis", _fake_redis_with_kwargs())
    def test_no_message_means_not_cancelled(self):
        fake_conn = MagicMock()
        fake_pubsub = MagicMock()
        fake_pubsub.get_message.return_value = None
        fake_conn.pubsub.return_value = fake_pubsub

        with TaskCancelWatcher("t1", connection=fake_conn) as watcher:
            # Give the watcher a brief window to confirm it stays calm.
            assert watcher.wait(timeout=0.2) is False
            assert watcher.cancelled is False

    @patch.object(task_cancel.RedisBase, "_redis", _fake_redis_with_kwargs())
    def test_pubsub_exception_inside_loop_does_not_propagate(self):
        """A redis disconnection inside the watcher thread must not
        crash the host task — the persistent flag is the safety net."""
        fake_conn = MagicMock()
        fake_pubsub = MagicMock()
        fake_pubsub.get_message.side_effect = RuntimeError("redis dropped")
        fake_conn.pubsub.return_value = fake_pubsub

        with TaskCancelWatcher("t1", connection=fake_conn) as watcher:
            # Thread will hit the exception, log it, and exit cleanly
            # via the finally-block. cancelled stays False.
            time.sleep(0.05)
            assert watcher.cancelled is False


class TestTaskCancelWatcherCleanup:
    @patch.object(task_cancel.RedisBase, "_redis", _fake_redis_with_kwargs())
    def test_exit_closes_pubsub_and_joins_thread(self):
        fake_conn = MagicMock()
        fake_pubsub = MagicMock()
        fake_pubsub.get_message.return_value = None
        fake_conn.pubsub.return_value = fake_pubsub

        watcher = TaskCancelWatcher("t1", connection=fake_conn)
        with watcher:
            captured_thread = watcher._thread
            assert captured_thread is not None
            assert captured_thread.is_alive()

        # __exit__ contract: pubsub closed, conn closed, thread joined.
        fake_pubsub.close.assert_called_once()
        fake_conn.close.assert_called_once()
        # join(timeout=2.0) was called; the thread should have exited.
        assert not captured_thread.is_alive()

    @patch.object(task_cancel.RedisBase, "_redis", _fake_redis_with_kwargs())
    def test_exit_is_idempotent_when_initial_check_fast_path(self):
        """When initial_check fires, no pubsub/thread were created.
        __exit__ must still complete without errors."""
        fake_conn = MagicMock()
        with TaskCancelWatcher("t1", initial_check=lambda: True, connection=fake_conn):
            pass
        # No subscribe ever happened, but conn.close is best-effort and
        # called regardless. No pubsub.close because pubsub was never built.
        fake_conn.close.assert_called_once()
        fake_conn.pubsub.assert_not_called()

    @patch.object(task_cancel.RedisBase, "_redis", _fake_redis_with_kwargs())
    def test_exit_swallows_close_errors(self):
        """A cleanup error must not mask the host task's exception."""
        fake_conn = MagicMock()
        fake_pubsub = MagicMock()
        fake_pubsub.get_message.return_value = None
        fake_pubsub.close.side_effect = RuntimeError("already closed")
        fake_conn.close.side_effect = RuntimeError("conn dropped")
        fake_conn.pubsub.return_value = fake_pubsub

        # Must not raise.
        with TaskCancelWatcher("t1", connection=fake_conn):
            pass


class TestTaskCancelWatcherWait:
    @patch.object(task_cancel.RedisBase, "_redis", _fake_redis_with_kwargs())
    def test_wait_returns_true_when_signal_arrives_via_set_event(self):
        """`wait()` is a thin wrapper over the internal Event — exercise
        it directly so we don't depend on the daemon thread's timing."""
        fake_conn = MagicMock()
        fake_pubsub = MagicMock()
        fake_pubsub.get_message.return_value = None
        fake_conn.pubsub.return_value = fake_pubsub

        with TaskCancelWatcher("t1", connection=fake_conn) as watcher:
            # Simulate the daemon firing.
            threading.Timer(0.05, watcher._event.set).start()
            assert watcher.wait(timeout=2.0) is True

    @patch.object(task_cancel.RedisBase, "_redis", _fake_redis_with_kwargs())
    def test_wait_returns_false_on_timeout(self):
        fake_conn = MagicMock()
        fake_pubsub = MagicMock()
        fake_pubsub.get_message.return_value = None
        fake_conn.pubsub.return_value = fake_pubsub

        with TaskCancelWatcher("t1", connection=fake_conn) as watcher:
            assert watcher.wait(timeout=0.05) is False
