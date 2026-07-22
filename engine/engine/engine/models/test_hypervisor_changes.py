"""Happy-path + malformed-row tests for `HypervisorChangesThread._process_change`.

These tests bypass `__init__` (which spawns threads / hits Redis) by using
`HypervisorChangesThread.__new__` and only wiring the pieces `_process_change`
actually touches: `q_orchestrator`.
"""

from queue import Queue

from changefeed_models.hypervisors_change import HypervisorsChange
from changefeed_models.hypervisors_row import HypervisorsRow

from engine.models.hypervisor_orchestrator import HypervisorChangesThread


def _thread() -> HypervisorChangesThread:
    t = HypervisorChangesThread.__new__(HypervisorChangesThread)
    t.q_orchestrator = Queue()
    return t


def test_enable_on_transition_emits_action():
    t = _thread()
    old = HypervisorsRow(id="h1", enabled=False, status="Offline", table="hypervisors")
    new = HypervisorsRow(id="h1", enabled=True, status="Offline", table="hypervisors")
    change = HypervisorsChange(old_val=old, new_val=new)

    t._process_change(change)

    action = t.q_orchestrator.get_nowait()
    assert action["type"] == "enable_hyper"
    assert action["hyp_id"] == "h1"
    assert action["enabled"] is True
    assert action["status"] == "Offline"


def test_disable_on_transition_emits_action():
    t = _thread()
    old = HypervisorsRow(id="h1", enabled=True, status="Online", table="hypervisors")
    new = HypervisorsRow(id="h1", enabled=False, status="Online", table="hypervisors")
    change = HypervisorsChange(old_val=old, new_val=new)

    t._process_change(change)

    action = t.q_orchestrator.get_nowait()
    assert action["type"] == "disable_hyper"
    assert action["hyp_id"] == "h1"
    assert action["enabled"] is False


def test_no_action_when_enabled_unchanged():
    t = _thread()
    old = HypervisorsRow(id="h1", enabled=True, status="Online", table="hypervisors")
    new = HypervisorsRow(id="h1", enabled=True, status="Online", table="hypervisors")
    change = HypervisorsChange(old_val=old, new_val=new)

    t._process_change(change)

    assert t.q_orchestrator.empty()


def test_create_offline_enabled_emits_enable_action():
    t = _thread()
    new = HypervisorsRow(id="h1", enabled=True, status="Offline", table="hypervisors")
    change = HypervisorsChange(old_val=None, new_val=new)

    t._process_change(change)

    action = t.q_orchestrator.get_nowait()
    assert action["type"] == "enable_hyper"
    assert action["hyp_id"] == "h1"


def test_only_forced_transition_emits_action():
    t = _thread()
    old = HypervisorsRow(
        id="h1", enabled=True, status="Online", only_forced=False, table="hypervisors"
    )
    new = HypervisorsRow(
        id="h1", enabled=True, status="Online", only_forced=True, table="hypervisors"
    )
    change = HypervisorsChange(old_val=old, new_val=new)

    t._process_change(change)

    action = t.q_orchestrator.get_nowait()
    assert action["type"] == "hyp_only_forced"
    assert action["hyp_id"] == "h1"


def test_missing_table_field_still_processes():
    """Task 13 dropped the `(x.table or False) == "hypervisors"` guard.

    A row with table=None should no longer silently drop — `_process_change`
    is invoked unconditionally for the hypervisors subscriber, and field
    transitions still produce actions.
    """
    t = _thread()
    old = HypervisorsRow(id="h1", enabled=False, status="Offline", table=None)
    new = HypervisorsRow(id="h1", enabled=True, status="Offline", table=None)
    change = HypervisorsChange(old_val=old, new_val=new)

    t._process_change(change)

    action = t.q_orchestrator.get_nowait()
    assert action["type"] == "enable_hyper"
    assert action["hyp_id"] == "h1"


def test_additional_properties_none_does_not_crash():
    """`(new_val.additional_properties or {}).get("thread_status", {})` must
    tolerate `additional_properties is None`."""
    t = _thread()
    old = HypervisorsRow(id="h1", enabled=False, status="Offline", table="hypervisors")
    new = HypervisorsRow(
        id="h1",
        enabled=True,
        status="Offline",
        table="hypervisors",
        additional_properties=None,
    )
    change = HypervisorsChange(old_val=old, new_val=new)

    t._process_change(change)

    action = t.q_orchestrator.get_nowait()
    assert action["thread_status"] == {}
