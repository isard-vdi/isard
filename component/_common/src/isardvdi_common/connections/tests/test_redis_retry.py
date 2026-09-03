# SPDX-License-Identifier: AGPL-3.0-or-later

"""``RedisRetry`` waits a redis outage out instead of failing the command, and
the storage workers depend on that. What it must not do is make the wait
invisible, or report a socket deadline as a lost connection.
"""

import logging
from unittest.mock import patch

import pytest
import redis
from isardvdi_common.connections.redis_retry import (
    LOUD_AFTER_ATTEMPTS,
    RETRY_INTERVAL,
    RedisRetry,
)


@pytest.fixture
def no_sleep():
    with patch("isardvdi_common.connections.redis_retry.sleep") as sleeper:
        yield sleeper


def _client():
    return RedisRetry.from_url("redis://:@isard-redis:6379/0")


def _raises_then_succeeds(errors):
    calls = {"n": 0}

    def execute(*args, **kwargs):
        if calls["n"] < len(errors):
            calls["n"] += 1
            raise errors[calls["n"] - 1]
        return "OK"

    return execute


class TestItStillSurvivesAnOutage:
    """The retry is unbounded on purpose and must stay that way."""

    def test_it_retries_until_the_command_succeeds(self, no_sleep):
        errors = [redis.ConnectionError("down")] * 20
        with patch.object(
            redis.Redis, "execute_command", _raises_then_succeeds(errors)
        ):
            assert _client().execute_command("PING") == "OK"
        assert no_sleep.call_count == 20

    def test_it_waits_the_same_interval_every_time(self, no_sleep):
        errors = [redis.ConnectionError("down")] * 3
        with patch.object(
            redis.Redis, "execute_command", _raises_then_succeeds(errors)
        ):
            _client().execute_command("PING")
        assert [c.args[0] for c in no_sleep.call_args_list] == [RETRY_INTERVAL] * 3

    def test_an_error_it_does_not_own_still_propagates(self, no_sleep):
        with patch.object(
            redis.Redis, "execute_command", side_effect=redis.ResponseError("WRONGTYPE")
        ):
            with pytest.raises(redis.ResponseError):
                _client().execute_command("GET", "x")


class TestTheWaitIsVisible:
    """It used to print(), so none of this reached the log pipeline at all."""

    def test_it_logs_through_the_module_logger(self, no_sleep, caplog):
        errors = [redis.ConnectionError("down")]
        with caplog.at_level(logging.WARNING):
            with patch.object(
                redis.Redis, "execute_command", _raises_then_succeeds(errors)
            ):
                _client().execute_command("PING")
        assert caplog.records
        assert caplog.records[0].name == "isardvdi_common.connections.redis_retry"

    def test_a_timeout_is_named_a_timeout_and_not_a_connection_error(
        self, no_sleep, caplog
    ):
        errors = [redis.TimeoutError("Timeout reading from socket")]
        with caplog.at_level(logging.WARNING):
            with patch.object(
                redis.Redis, "execute_command", _raises_then_succeeds(errors)
            ):
                _client().execute_command("BLPOP", "q", 0)
        assert "TimeoutError" in caplog.text
        assert "ConnectionError" not in caplog.text

    def test_a_connection_error_is_named_a_connection_error(self, no_sleep, caplog):
        errors = [redis.ConnectionError("socket closed")]
        with caplog.at_level(logging.WARNING):
            with patch.object(
                redis.Redis, "execute_command", _raises_then_succeeds(errors)
            ):
                _client().execute_command("PING")
        assert "ConnectionError" in caplog.text

    def test_the_command_is_named_so_the_stuck_call_is_identifiable(
        self, no_sleep, caplog
    ):
        errors = [redis.TimeoutError("deadline")]
        with caplog.at_level(logging.WARNING):
            with patch.object(
                redis.Redis, "execute_command", _raises_then_succeeds(errors)
            ):
                _client().execute_command("BLPOP", "rq:queue:storage", 0)
        assert "BLPOP" in caplog.text

    def test_a_blip_stays_at_warning(self, no_sleep, caplog):
        errors = [redis.ConnectionError("down")] * (LOUD_AFTER_ATTEMPTS - 1)
        with caplog.at_level(logging.WARNING):
            with patch.object(
                redis.Redis, "execute_command", _raises_then_succeeds(errors)
            ):
                _client().execute_command("PING")
        assert {r.levelno for r in caplog.records} == {logging.WARNING}

    def test_a_loop_that_will_not_end_escalates_to_error(self, no_sleep, caplog):
        errors = [redis.ConnectionError("down")] * (LOUD_AFTER_ATTEMPTS + 2)
        with caplog.at_level(logging.WARNING):
            with patch.object(
                redis.Redis, "execute_command", _raises_then_succeeds(errors)
            ):
                _client().execute_command("PING")
        assert logging.ERROR in {r.levelno for r in caplog.records}
        assert caplog.records[-1].levelno == logging.ERROR
