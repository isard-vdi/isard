# SPDX-License-Identifier: AGPL-3.0-or-later

"""The background user-log write: failures are retrieved, reported and backed off."""

import asyncio
import gc
import logging
import threading
from types import SimpleNamespace

import pytest
from api.dependencies import jwt_token
from api.dependencies.jwt_token import TokenFastAPI
from rethinkdb.errors import ReqlNonExistenceError


def payload(user_id="u1"):
    return {"exp": 1, "data": {"user_id": user_id, "group_id": "g"}}


class FakeLogsUsers:
    def __init__(self, error=None, gate=None):
        self.error = error
        self.gate = gate
        self.calls = []

    def __call__(self, payload, request_ip=None, request_user_agent=None):
        self.calls.append(payload["data"]["user_id"])
        if self.gate:
            self.gate.wait(5)
        if self.error:
            raise self.error


@pytest.fixture(autouse=True)
def state(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(jwt_token, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(jwt_token._LogUserFailures, "retry_at", 0.0)
    monkeypatch.setattr(jwt_token._LogUserFailures, "reported_at", float("-inf"))
    monkeypatch.setattr(jwt_token._LogUserFailures, "unreported", 0)
    jwt_token._LOG_USER_TASKS.clear()
    jwt_token._LOG_USER_IN_FLIGHT.clear()
    yield clock
    jwt_token._LOG_USER_TASKS.clear()
    jwt_token._LOG_USER_IN_FLIGHT.clear()


def use(monkeypatch, fake):
    monkeypatch.setattr(jwt_token, "LogsUsers", fake)
    return fake


async def drain():
    while jwt_token._LOG_USER_TASKS:
        await asyncio.sleep(0.01)


def run(*steps):
    """Run ``log_user`` for each user id (or a callable) inside one loop; return unhandled loop errors."""
    unhandled = []

    async def main():
        asyncio.get_running_loop().set_exception_handler(
            lambda loop, ctx: unhandled.append(ctx)
        )
        for step in steps:
            if callable(step):
                step()
            else:
                TokenFastAPI.log_user(payload(step))
            await drain()
        gc.collect()

    asyncio.run(main())
    return unhandled


def test_a_failed_write_is_retrieved_and_logged(monkeypatch, caplog):
    use(monkeypatch, FakeLogsUsers(error=ConnectionError("db down")))
    with caplog.at_level(logging.WARNING):
        unhandled = run("u1")
    assert unhandled == []
    assert "Unable to update user logs (1 failed writes)" in caplog.text
    assert "db down" in caplog.text


def test_no_write_starts_while_backing_off(monkeypatch, state):
    fake = use(monkeypatch, FakeLogsUsers(error=ConnectionError("db down")))

    def later():
        state[0] += jwt_token.LOG_USER_RETRY_S

    run("u1", "u2", "u3", later, "u4")
    assert fake.calls == ["u1", "u4"]


def test_a_data_error_is_reported_without_pausing_other_users(monkeypatch, caplog):
    fake = use(monkeypatch, FakeLogsUsers(error=ReqlNonExistenceError("no user")))
    with caplog.at_level(logging.WARNING):
        run("u1", "u2")
    assert fake.calls == ["u1", "u2"]
    assert "no user" in caplog.text


def test_failures_are_reported_once_per_interval_with_a_count(
    monkeypatch, caplog, state
):
    gate = threading.Event()
    use(monkeypatch, FakeLogsUsers(error=ConnectionError("db down"), gate=gate))

    async def main():
        for user in ("u1", "u2", "u3"):
            TokenFastAPI.log_user(payload(user))
        gate.set()
        await drain()

    with caplog.at_level(logging.WARNING):
        asyncio.run(main())
    warnings = [r for r in caplog.records if "Unable to update user logs" in r.message]
    assert len(warnings) == 1
    assert jwt_token._LogUserFailures.unreported == 2


def test_one_write_in_flight_per_user(monkeypatch):
    gate = threading.Event()
    fake = use(monkeypatch, FakeLogsUsers(gate=gate))

    async def main():
        TokenFastAPI.log_user(payload("u1"))
        TokenFastAPI.log_user(payload("u1"))
        TokenFastAPI.log_user(payload("u2"))
        gate.set()
        await drain()
        TokenFastAPI.log_user(payload("u1"))
        await drain()

    asyncio.run(main())
    assert fake.calls == ["u1", "u2", "u1"]


def test_a_successful_write_does_not_back_off(monkeypatch, caplog):
    fake = use(monkeypatch, FakeLogsUsers())
    with caplog.at_level(logging.WARNING):
        run("u1", "u2")
    assert fake.calls == ["u1", "u2"]
    assert "Unable to update user logs" not in caplog.text
