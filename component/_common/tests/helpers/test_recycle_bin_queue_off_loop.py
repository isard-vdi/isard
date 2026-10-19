# SPDX-License-Identifier: AGPL-3.0-or-later

"""The delete queue never runs a database call on the event loop thread.

The queue worker lives on apiv4's event loop: a query run there stalls every
request until it returns, and a hung one freezes the whole API.
"""

import asyncio
import contextlib
import threading
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers import recycle_bin as mod


@pytest.fixture
def queue(monkeypatch):
    monkeypatch.setattr(mod.RecycleBinDeleteQueue, "_instance", None)
    monkeypatch.setattr(mod.RecycleBinDeleteQueue, "_lock", None)
    monkeypatch.setattr(mod.RecycleBinDeleteQueue, "_initialized", False)
    monkeypatch.setattr(
        mod.RecycleBinDeleteQueue, "_rdb_context", lambda self: contextlib.nullcontext()
    )
    monkeypatch.setattr(mod.Helpers, "claim_for_purge", lambda *a: True)
    monkeypatch.setattr(mod.Helpers, "add_log", lambda *a: None)
    return mod.RecycleBinDeleteQueue()


@pytest.fixture
def threads():
    return []


@pytest.fixture
def fake_r(monkeypatch, threads):
    def _rows(rows):
        def run(*_a, **_kw):
            threads.append(("query", threading.get_ident()))
            return rows

        fake = MagicMock(name="r")
        chain = fake.table.return_value.get_all.return_value
        chain.pluck.return_value.run.side_effect = run
        chain.filter.return_value.pluck.return_value.__getitem__.return_value.run.side_effect = (
            run
        )
        monkeypatch.setattr(mod, "r", fake)

    return _rows


def _entry(threads, item_type="desktop", users=(), error=None):
    class _Entry:
        def __init__(self, id):
            threads.append(("load", threading.get_ident()))
            self.id = id
            self.status = "queued"
            self.item_type = item_type
            self.users = list(users)
            self.groups = []
            self.categories = []

        def delete_storage(self, user_id):
            threads.append(("delete_storage", threading.get_ident()))
            if error:
                raise error

    return _Entry


def _run(coro_fn):
    async def main():
        loop_thread = threading.get_ident()
        await coro_fn()
        return loop_thread

    return asyncio.run(main())


def test_initialize_reads_the_queued_entries_off_the_loop(queue, fake_r, threads):
    fake_r([{"id": "rb1", "agent_id": "u1"}])

    async def go():
        await queue.initialize()
        assert (await queue.queue.get())["recycle_bin_id"] == "rb1"

    loop_thread = _run(go)
    assert threads and all(t != loop_thread for _, t in threads), threads


def test_a_purge_runs_its_database_work_off_the_loop(
    queue, fake_r, threads, monkeypatch
):
    fake_r(["rb-dep"])
    monkeypatch.setattr(
        mod, "RecycleBin", _entry(threads, item_type="user", users=[{"id": "u2"}])
    )

    async def go():
        queue.queue = asyncio.Queue()
        await queue.perform_operation("rb1", "admin")
        assert (await queue.queue.get())["recycle_bin_id"] == "rb-dep"

    loop_thread = _run(go)
    assert [step for step, _ in threads] == ["load", "delete_storage", "query"]
    assert all(t != loop_thread for _, t in threads), threads


def test_a_failed_purge_gives_back_its_claim_off_the_loop(queue, threads, monkeypatch):
    monkeypatch.setattr(mod, "RecycleBin", _entry(threads, error=RuntimeError("x")))
    monkeypatch.setattr(
        mod.Helpers,
        "claim_status",
        lambda *a: threads.append(("claim_status", threading.get_ident())),
    )

    loop_thread = _run(lambda: queue.perform_operation("rb1", "admin"))
    assert [step for step, _ in threads] == ["load", "delete_storage", "claim_status"]
    assert all(t != loop_thread for _, t in threads), threads


def test_a_slow_purge_does_not_hold_up_other_coroutines(queue, monkeypatch):
    class _Slow:
        def __init__(self, id):
            self.status = "queued"
            self.item_type = "desktop"

        def delete_storage(self, user_id):
            threading.Event().wait(0.5)

    monkeypatch.setattr(mod, "RecycleBin", _Slow)

    async def go():
        loop = asyncio.get_running_loop()
        purge = asyncio.create_task(queue.perform_operation("rb1", "admin"))
        start = loop.time()
        await asyncio.sleep(0.01)
        lag = loop.time() - start
        await purge
        assert lag < 0.25, lag

    _run(go)
