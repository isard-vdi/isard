# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for RedisStreamConsumer — the single consumer wiring used by
every engine thread that reads from `stream:<table>`. Covers the init
defaults, group creation idempotency, and the pending-message replay
path. The main `run()` loop is not unit-tested here because it blocks
forever — integration tests live downstream.
"""

import json
import logging
import threading
from unittest.mock import MagicMock, patch

import pytest
import redis
from isardvdi_common.redis_stream import (
    PAYLOAD_LOG_CHARS,
    RedisStreamConsumer,
    _payload_summary,
)


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


class TestDroppedMessagesAreLoud:
    """A message the handler rejects is acked on purpose -- redelivering it
    forever would wedge the consumer behind one bad change. That trade is only
    acceptable while the loss is visible, so what the log line carries is part
    of the contract, not decoration.
    """

    @staticmethod
    def _one_message(payload, msg_id=b"1-0", stream="stream:a"):
        fake_r = MagicMock()
        fake_r.xreadgroup.side_effect = [[(stream, [(msg_id, {"data": payload})])], []]
        return fake_r

    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_log_names_the_message_stream_and_group(self, mock_from_url, caplog):
        payload = json.dumps({"table": "users", "change": {"old_val": {"id": "u1"}}})
        mock_from_url.return_value = self._one_message(payload)

        def failing_handler(_):
            raise RuntimeError("boom")

        c = RedisStreamConsumer(streams=["stream:a"], group="vpn-wireguard")
        with caplog.at_level(logging.ERROR):
            c._process_pending(failing_handler)

        assert "1-0" in caplog.text
        assert "stream:a" in caplog.text
        assert "vpn-wireguard" in caplog.text

    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_log_carries_the_payload_so_the_lost_change_is_identifiable(
        self, mock_from_url, caplog
    ):
        payload = json.dumps({"table": "users", "change": {"old_val": {"id": "u-42"}}})
        mock_from_url.return_value = self._one_message(payload)

        c = RedisStreamConsumer(streams=["stream:a"], group="g1")
        with caplog.at_level(logging.ERROR):
            c._process_pending(MagicMock(side_effect=RuntimeError("boom")))

        assert "u-42" in caplog.text

    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_log_carries_the_handler_traceback(self, mock_from_url, caplog):
        mock_from_url.return_value = self._one_message(json.dumps({"table": "users"}))

        c = RedisStreamConsumer(streams=["stream:a"], group="g1")
        with caplog.at_level(logging.ERROR):
            c._process_pending(MagicMock(side_effect=RuntimeError("the-real-cause")))

        assert "the-real-cause" in caplog.text
        assert "Traceback" in caplog.text

    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_malformed_json_is_logged_and_acked(self, mock_from_url, caplog):
        """The handler never runs for a payload that will not parse; the
        message must still be reported and acked."""
        fake_r = self._one_message("{not json at all")
        mock_from_url.return_value = fake_r
        handler = MagicMock()

        c = RedisStreamConsumer(streams=["stream:a"], group="g1")
        with caplog.at_level(logging.ERROR):
            c._process_pending(handler)

        handler.assert_not_called()
        fake_r.xack.assert_called_once_with("stream:a", "g1", b"1-0")
        assert "1-0" in caplog.text

    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_a_message_with_no_data_field_is_logged_and_acked(
        self, mock_from_url, caplog
    ):
        fake_r = MagicMock()
        fake_r.xreadgroup.side_effect = [[("stream:a", [(b"1-0", {})])], []]
        mock_from_url.return_value = fake_r

        c = RedisStreamConsumer(streams=["stream:a"], group="g1")
        with caplog.at_level(logging.ERROR):
            c._process_pending(MagicMock())

        fake_r.xack.assert_called_once_with("stream:a", "g1", b"1-0")
        assert "1-0" in caplog.text

    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_a_successful_message_logs_no_error(self, mock_from_url, caplog):
        mock_from_url.return_value = self._one_message(json.dumps({"table": "users"}))

        c = RedisStreamConsumer(streams=["stream:a"], group="g1")
        with caplog.at_level(logging.ERROR):
            c._process_pending(MagicMock())

        assert caplog.text == ""

    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_one_bad_message_does_not_stop_the_ones_behind_it(self, mock_from_url):
        good = json.dumps({"table": "users", "change": {"new_val": {"id": "u2"}}})
        bad = json.dumps({"table": "users", "change": {"new_val": {"id": "u1"}}})
        fake_r = MagicMock()
        fake_r.xreadgroup.side_effect = [
            [("stream:a", [(b"1-0", {"data": bad}), (b"2-0", {"data": good})])],
            [],
        ]
        mock_from_url.return_value = fake_r

        seen = []

        def handler(data):
            peer_id = data["change"]["new_val"]["id"]
            if peer_id == "u1":
                raise RuntimeError("boom")
            seen.append(peer_id)

        c = RedisStreamConsumer(streams=["stream:a"], group="g1")
        c._process_pending(handler)

        assert seen == ["u2"]
        assert fake_r.xack.call_count == 2


class TestRunLoopDropsAreLoudToo:
    """The steady-state loop must behave exactly like the pending replay: the
    two paths are separate code and drifted apart before."""

    @staticmethod
    def _stopping_redis(payload, stop_event):
        """``run()`` replays pending messages before entering its loop, and
        that replay drains ``xreadgroup`` until it comes back empty. So: give
        the replay nothing, then one message to the loop, then stop."""
        fake_r = MagicMock()
        calls = {"n": 0}

        def xreadgroup(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:  # the pending replay
                return []
            stop_event.set()  # one pass through the loop, then leave it
            return [("stream:a", [(b"9-0", {"data": payload})])]

        fake_r.xreadgroup.side_effect = xreadgroup
        return fake_r

    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_handler_failure_is_logged_and_acked_in_the_run_loop(
        self, mock_from_url, caplog
    ):
        stop = threading.Event()
        payload = json.dumps({"table": "users", "change": {"old_val": {"id": "u-99"}}})
        fake_r = self._stopping_redis(payload, stop)
        mock_from_url.return_value = fake_r

        c = RedisStreamConsumer(streams=["stream:a"], group="g1")
        with caplog.at_level(logging.ERROR):
            c.run(MagicMock(side_effect=RuntimeError("boom")), stop_event=stop)

        fake_r.xack.assert_any_call("stream:a", "g1", b"9-0")
        assert "9-0" in caplog.text
        assert "u-99" in caplog.text

    @patch("isardvdi_common.redis_stream.redis.from_url")
    def test_successful_run_loop_message_logs_no_error(self, mock_from_url, caplog):
        stop = threading.Event()
        fake_r = self._stopping_redis(json.dumps({"table": "users"}), stop)
        mock_from_url.return_value = fake_r
        handler = MagicMock()

        c = RedisStreamConsumer(streams=["stream:a"], group="g1")
        with caplog.at_level(logging.ERROR):
            c.run(handler, stop_event=stop)

        assert handler.call_count == 1
        assert caplog.text == ""


class TestPayloadSummary:
    """It runs inside an except block. If it can raise, it replaces the
    handler's traceback with its own and the real cause is lost."""

    def test_short_payload_is_kept_whole(self):
        assert _payload_summary({"data": '{"id": "u1"}'}) == '{"id": "u1"}'

    def test_long_payload_is_truncated_and_marked(self):
        summary = _payload_summary({"data": "x" * (PAYLOAD_LOG_CHARS + 50)})
        assert summary == "x" * PAYLOAD_LOG_CHARS + "..."

    def test_payload_exactly_at_the_limit_is_not_marked(self):
        summary = _payload_summary({"data": "x" * PAYLOAD_LOG_CHARS})
        assert summary == "x" * PAYLOAD_LOG_CHARS
        assert not summary.endswith("...")

    @pytest.mark.parametrize(
        "fields",
        [
            pytest.param({}, id="no-data-key"),
            pytest.param({"data": None}, id="data-is-null"),
            pytest.param({"data": 42}, id="data-is-not-a-string"),
            pytest.param({"data": object()}, id="data-is-unsliceable"),
        ],
    )
    def test_junk_never_raises(self, fields):
        # Whatever it returns, it must return -- never raise out of an except.
        assert isinstance(_payload_summary(fields), str)

    def test_a_fields_object_that_explodes_is_survived(self):
        class Exploding:
            def get(self, *args, **kwargs):
                raise RuntimeError("nope")

        assert _payload_summary(Exploding()) == "<unavailable>"
