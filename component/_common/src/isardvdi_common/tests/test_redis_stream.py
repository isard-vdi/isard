# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for RedisStreamConsumer — the single consumer wiring used by
every engine thread that reads from `stream:<table>`. Covers the init
defaults, group creation idempotency, and the pending-message replay
path. The main `run()` loop is not unit-tested here because it blocks
forever — integration tests live downstream.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import redis
from isardvdi_common.redis_stream import RedisStreamConsumer


class TestInit:
    def test_default_consumer_name_includes_hostname_and_pid(self):
        c = RedisStreamConsumer(streams=["stream:domains"], group="engine-domains")
        # "<hostname>-<pid>" format — both segments non-empty.
        parts = c.consumer.split("-")
        assert len(parts) >= 2
        assert parts[-1].isdigit()

    def test_explicit_consumer_name_overrides_default(self):
        c = RedisStreamConsumer(
            streams=["stream:domains"],
            group="engine-domains",
            consumer="worker-3",
        )
        assert c.consumer == "worker-3"

    def test_streams_and_group_stored(self):
        c = RedisStreamConsumer(streams=["stream:a", "stream:b"], group="g1")
        assert c.streams == ["stream:a", "stream:b"]
        assert c.group == "g1"

    def test_redis_not_connected_until_first_op(self):
        c = RedisStreamConsumer(streams=["x"], group="g")
        assert c._redis is None


class TestEnsureGroups:
    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_creates_group_for_each_stream(self, mock_from_url):
        fake_r = MagicMock()
        mock_from_url.return_value = fake_r
        c = RedisStreamConsumer(streams=["stream:a", "stream:b"], group="g1")
        c._ensure_groups()
        assert fake_r.xgroup_create.call_count == 2
        fake_r.xgroup_create.assert_any_call("stream:a", "g1", id="0", mkstream=True)
        fake_r.xgroup_create.assert_any_call("stream:b", "g1", id="0", mkstream=True)

    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_busygroup_error_is_swallowed(self, mock_from_url):
        # BUSYGROUP means the group already exists on the stream — safe to ignore.
        fake_r = MagicMock()
        fake_r.xgroup_create.side_effect = redis.ResponseError(
            "BUSYGROUP Consumer Group name already exists"
        )
        mock_from_url.return_value = fake_r
        c = RedisStreamConsumer(streams=["stream:a"], group="g1")
        # Must not raise
        c._ensure_groups()

    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_other_response_error_propagates(self, mock_from_url):
        fake_r = MagicMock()
        fake_r.xgroup_create.side_effect = redis.ResponseError("ERR something else")
        mock_from_url.return_value = fake_r
        c = RedisStreamConsumer(streams=["stream:a"], group="g1")
        with pytest.raises(redis.ResponseError):
            c._ensure_groups()

    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_connection_is_cached(self, mock_from_url):
        fake_r = MagicMock()
        mock_from_url.return_value = fake_r
        c = RedisStreamConsumer(streams=["stream:a"], group="g1")
        c._ensure_groups()
        c._ensure_groups()
        # from_url called exactly once despite two _ensure_groups calls
        assert mock_from_url.call_count == 1


class TestProcessPending:
    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_handler_called_for_each_pending_message(self, mock_from_url):
        fake_r = MagicMock()
        payload = json.dumps({"table": "domains", "change": {"new_val": {"id": "d1"}}})
        # First call returns one batch; second call returns empty to end the loop.
        fake_r.xreadgroup.side_effect = [
            [("stream:a", [(b"1-0", {"data": payload})])],
            [],
        ]
        mock_from_url.return_value = fake_r

        handler = MagicMock()
        c = RedisStreamConsumer(streams=["stream:a"], group="g1", consumer="w1")
        c._process_pending(handler)

        handler.assert_called_once_with(
            {"table": "domains", "change": {"new_val": {"id": "d1"}}}
        )
        fake_r.xack.assert_called_once_with("stream:a", "g1", b"1-0")

    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_handler_exception_is_logged_and_message_still_acked(self, mock_from_url):
        """A bad payload must not block the stream — ack it anyway so the
        consumer moves past it."""
        fake_r = MagicMock()
        payload = json.dumps({"table": "domains"})
        fake_r.xreadgroup.side_effect = [
            [("stream:a", [(b"1-0", {"data": payload})])],
            [],
        ]
        mock_from_url.return_value = fake_r

        def failing_handler(_):
            raise RuntimeError("boom")

        c = RedisStreamConsumer(streams=["stream:a"], group="g1", consumer="w1")
        c._process_pending(failing_handler)  # must not raise
        fake_r.xack.assert_called_once_with("stream:a", "g1", b"1-0")

    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_no_pending_returns_immediately(self, mock_from_url):
        fake_r = MagicMock()
        fake_r.xreadgroup.return_value = []
        mock_from_url.return_value = fake_r
        handler = MagicMock()
        c = RedisStreamConsumer(streams=["stream:a"], group="g1")
        c._process_pending(handler)
        handler.assert_not_called()
        fake_r.xack.assert_not_called()
