# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for HypervisorChangesThread._process_change — the pure
state-machine that translates RethinkDB changefeed events into
queue actions for the hypervisor orchestrator.

The class inherits from threading.Thread; we bypass `__init__` via
`__new__` so we don't start a thread, and set only the attributes
`_process_change` reads (`q_orchestrator`, `_stop_event`).

Post-refactor (commit ``14ab01bb5``): ``_process_change`` receives a
typed ``HypervisorsChange`` envelope exposing ``.new_val`` / ``.old_val``
``HypervisorsRow`` attributes, not raw dicts. The engine-stop signal
is handled upstream in ``run()``/``handler()`` (it parses engine rows
and sets ``_stop_event`` before ever calling ``_process_change``), so
the engine-stop cases are no longer exercised here.
"""

from queue import Queue
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from changefeed_models.hypervisors_row import HypervisorsRow

from engine.models.hypervisor_orchestrator import HypervisorChangesThread


def _row(payload):
    """Build a ``HypervisorsRow`` from a dict payload (or None)."""
    if payload is None:
        return None
    return HypervisorsRow.model_validate(payload)


def _change(new_val=None, old_val=None):
    """A change-envelope-shaped object with ``.new_val`` / ``.old_val``
    attrs. ``SimpleNamespace`` is enough — ``_process_change`` only
    reads those two attrs.
    """
    return SimpleNamespace(new_val=_row(new_val), old_val=_row(old_val))


def _make_thread():
    """Construct a minimal instance without touching threading.Thread.__init__."""
    t = HypervisorChangesThread.__new__(HypervisorChangesThread)
    t.q_orchestrator = Queue()
    t._stop_event = Event()
    return t


class TestHypervisorDelete:
    @patch("engine.models.hypervisor_orchestrator.update_domains_in_deleted_hyper")
    @patch("engine.models.hypervisor_orchestrator.remove_hyp_thread_status")
    def test_deleted_hypervisor_cleans_up_threads_and_domains(
        self, mock_remove, mock_update
    ):
        t = _make_thread()
        t._process_change(_change(old_val={"table": "hypervisors", "id": "h1"}))
        mock_remove.assert_called_once_with("h1")
        mock_update.assert_called_once_with("h1")


class TestHypervisorCreate:
    def test_offline_enabled_creation_queues_enable_hyper(self):
        t = _make_thread()
        new_val = {
            "id": "h1",
            "table": "hypervisors",
            "status": "Offline",
            "enabled": True,
            "capabilities": {"hyper": True},
            "hypervisors_pools": ["default"],
        }
        t._process_change(_change(new_val=new_val))
        action = t.q_orchestrator.get_nowait()
        assert action["type"] == "enable_hyper"
        assert action["hyp_id"] == "h1"
        assert action["capabilities"] == {"hyper": True}
        assert action["enabled"] is True
        assert action["status"] == "Offline"

    def test_online_creation_not_queued(self):
        # Only Offline + enabled triggers the initial enable — an
        # already-Online new hypervisor doesn't need kicking.
        t = _make_thread()
        new_val = {
            "id": "h1",
            "table": "hypervisors",
            "status": "Online",
            "enabled": True,
        }
        t._process_change(_change(new_val=new_val))
        assert t.q_orchestrator.empty()

    def test_disabled_creation_not_queued(self):
        t = _make_thread()
        new_val = {
            "id": "h1",
            "table": "hypervisors",
            "status": "Offline",
            "enabled": False,
        }
        t._process_change(_change(new_val=new_val))
        assert t.q_orchestrator.empty()


class TestHypervisorEnableDisableTransitions:
    def _mk(self, old_enabled, new_enabled, **extra):
        old_val = {
            "id": "h1",
            "table": "hypervisors",
            "status": "Online",
            "enabled": old_enabled,
        }
        new_val = dict(old_val)
        new_val["enabled"] = new_enabled
        new_val.update(extra)
        return _change(new_val=new_val, old_val=old_val)

    def test_enable_transition_queues_enable_hyper(self):
        t = _make_thread()
        t._process_change(self._mk(old_enabled=False, new_enabled=True))
        action = t.q_orchestrator.get_nowait()
        assert action["type"] == "enable_hyper"

    def test_disable_transition_queues_disable_hyper(self):
        t = _make_thread()
        t._process_change(self._mk(old_enabled=True, new_enabled=False))
        action = t.q_orchestrator.get_nowait()
        assert action["type"] == "disable_hyper"

    def test_no_enabled_change_does_not_queue_enable_or_disable(self):
        t = _make_thread()
        # Neither enabled flag changed; other fields may tick but no
        # enable/disable event is queued.
        t._process_change(self._mk(old_enabled=True, new_enabled=True))
        drained = []
        while not t.q_orchestrator.empty():
            drained.append(t.q_orchestrator.get_nowait())
        assert not any(a["type"] in ("enable_hyper", "disable_hyper") for a in drained)


class TestOnlyForcedTransition:
    def test_only_forced_false_to_true_queues_only_forced(self):
        t = _make_thread()
        old_val = {
            "id": "h1",
            "table": "hypervisors",
            "status": "Online",
            "enabled": True,
            "only_forced": False,
            "gpu_only": False,
        }
        new_val = dict(old_val)
        new_val["only_forced"] = True
        t._process_change(_change(new_val=new_val, old_val=old_val))
        # Drain queue and look for hyp_only_forced
        events = []
        while not t.q_orchestrator.empty():
            events.append(t.q_orchestrator.get_nowait())
        assert any(e["type"] == "hyp_only_forced" for e in events)

    def test_gpu_only_false_to_true_queues_only_forced(self):
        t = _make_thread()
        old_val = {
            "id": "h1",
            "table": "hypervisors",
            "status": "Online",
            "enabled": True,
            "only_forced": False,
            "gpu_only": False,
        }
        new_val = dict(old_val)
        new_val["gpu_only"] = True
        t._process_change(_change(new_val=new_val, old_val=old_val))
        events = []
        while not t.q_orchestrator.empty():
            events.append(t.q_orchestrator.get_nowait())
        assert any(e["type"] == "hyp_only_forced" for e in events)

    def test_true_to_false_does_not_queue(self):
        t = _make_thread()
        old_val = {
            "id": "h1",
            "table": "hypervisors",
            "status": "Online",
            "enabled": True,
            "only_forced": True,
            "gpu_only": False,
        }
        new_val = dict(old_val)
        new_val["only_forced"] = False
        t._process_change(_change(new_val=new_val, old_val=old_val))
        events = []
        while not t.q_orchestrator.empty():
            events.append(t.q_orchestrator.get_nowait())
        assert not any(e["type"] == "hyp_only_forced" for e in events)


class TestExceptionTolerance:
    def test_unexpected_structure_is_swallowed(self):
        """The outer try/except on _process_change guards the consumer
        loop — a bad payload shouldn't crash the thread. Pass a bare
        namespace with no attributes; reading ``.new_val`` raises,
        production catches it, the method returns cleanly."""
        t = _make_thread()
        t._process_change(SimpleNamespace())  # must not raise
