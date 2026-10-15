"""A domain's lifecycle events are applied one at a time, in the order libvirt raised them."""

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

_rethinkdb_stubs = {
    name: sys.modules.pop(name)
    for name in list(sys.modules)
    if name == "rethinkdb" or name.startswith("rethinkdb.")
}
try:
    import engine.controllers.events_recolector as er
finally:
    sys.modules.update(_rethinkdb_stubs)

for _name in ("log", "logs"):
    if not hasattr(er, _name):
        setattr(er, _name, MagicMock(name=f"events_recolector.{_name}"))

URI = "qemu+ssh://root@hyp1:2022/system"
DOM = "d9cf9dc9-841c-4bdc-996d-945c675b81f5"


def _wait_for(predicate, what, deadline=5):
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.01)
    pytest.fail(f"waited {deadline}s for {what}")


def test_a_domains_events_run_in_order_even_when_the_first_is_slow():
    pool = ThreadPoolExecutor(max_workers=8)
    dispatcher = er.PerKeySerialDispatcher(pool)
    applied = []

    def apply(name, delay):
        time.sleep(delay)
        applied.append(name)

    dispatcher.submit(DOM, apply, "Started", 0.2)
    dispatcher.submit(DOM, apply, "Stopped", 0)

    _wait_for(lambda: len(applied) == 2, "both events")
    pool.shutdown()
    assert applied == ["Started", "Stopped"]


def test_a_failing_event_does_not_stall_the_ones_behind_it():
    pool = ThreadPoolExecutor(max_workers=2)
    dispatcher = er.PerKeySerialDispatcher(pool)
    applied = []

    def boom():
        raise RuntimeError("db down")

    dispatcher.submit(DOM, boom)
    dispatcher.submit(DOM, applied.append, "Stopped")

    _wait_for(lambda: applied == ["Stopped"], "the event behind the failure")
    pool.shutdown()


def test_the_callback_applies_a_booted_and_a_destroyed_of_one_domain_in_order(
    monkeypatch,
):
    """The race that left a desktop Started with nothing running: the Booted
    write landed after the Destroyed one."""
    applied = []
    first = threading.Event()

    def process(conn_uri, dom_name, event, detail, opaque, event_time):
        if event == 2:
            first.wait(0.3)
        applied.append(er.domEventToString(event))

    monkeypatch.setattr(er, "_process_domain_event_async", process)
    conn = MagicMock()
    conn.getURI.return_value = URI
    dom = MagicMock()
    dom.name.return_value = DOM

    er.myDomainEventCallbackRethink(conn, dom, 2, 0, None)
    er.myDomainEventCallbackRethink(conn, dom, 5, 1, None)

    _wait_for(lambda: len(applied) == 2, "both events")
    assert applied == ["Started", "Stopped"]
