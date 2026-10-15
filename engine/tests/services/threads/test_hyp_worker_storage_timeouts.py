"""A libvirt call that times out never leaves a terminal status behind."""

import queue
from concurrent.futures import Future
from unittest.mock import MagicMock

import pytest
from libvirt import libvirtError

from engine.services.lib import domain_guard
from engine.services.lib.libvirt_timeout import LibvirtTimeoutError
from engine.services.threads import hyp_worker_thread as mod
from engine.services.threads.hyp_worker_thread import HypWorkerThread

DOMAIN = "_admin_dsk-1"
ARMED = []


@pytest.fixture(autouse=True)
def env(monkeypatch):
    """Record every status write and scheduled retry; no Redis, no timers."""
    monkeypatch.setattr(domain_guard, "_mirror", lambda *a: None)
    domain_guard._held.clear()
    writes = []
    monkeypatch.setattr(
        mod,
        "update_domain_status",
        lambda status, domain_id, **kw: writes.append((status, domain_id, kw)),
    )
    for name in ("log_action", "update_vgpu_info_if_stopped", "live_xml_cache"):
        monkeypatch.setattr(mod, name, MagicMock())
    status = {"value": "Stopping"}
    monkeypatch.setattr(mod, "get_domain_status", lambda domain_id: status["value"])
    timers = []

    class FakeTimer:
        def __init__(self, delay, fn, args=()):
            timers.append((delay, fn, args))
            self.daemon = False
            self.cancelled = False
            ARMED.append(self)

        def start(self):
            pass

        def cancel(self):
            self.cancelled = True

    ARMED.clear()

    monkeypatch.setattr(mod.threading, "Timer", FakeTimer)
    yield writes, timers, status
    domain_guard._held.clear()


def _worker(calls):
    """A worker whose libvirt calls answer from ``calls``: an exception to
    raise, or a value to return, per operation name prefix."""
    w = HypWorkerThread.__new__(HypWorkerThread)
    w.hyp_id = "hyp-1"
    w.stop = False
    w.queue_actions = queue.Queue()
    w._stop_retries = {}
    w._stop_timers = {}
    w._inflight_calls = {}
    w.h = MagicMock()
    w.viewer = {}
    w.hostname = "hyp-1"
    w._cleanup_queued_actions = MagicMock()
    w._is_old_ovs_hypervisor = lambda: False
    w.executed = []

    def execute(func, args=(), kwargs=None, operation_name="", **_):
        w.executed.append(operation_name)
        for prefix, answer in calls.items():
            if operation_name.startswith(prefix):
                if isinstance(answer, BaseException):
                    raise answer
                return answer
        return MagicMock()

    w._execute_libvirt_with_timeout = execute
    return w


def _timeout(operation, future=None):
    return LibvirtTimeoutError(operation, 30, "hyp-1", future=future)


def _statuses(writes):
    return [s for s, _, _ in writes]


def _drain(w):
    actions = []
    while not w.queue_actions.empty():
        actions.append(w.queue_actions.get_nowait())
    return actions


class TestStopTimeout:
    def action(self):
        return {"type": "stop_domain", "id_domain": DOMAIN}

    def test_a_destroy_timeout_stays_stopping_and_is_retried(self, env):
        writes, timers, _ = env
        w = _worker({"domain.destroy": _timeout("domain.destroy", Future())})

        w._handle_stop_domain(self.action(), 0.0, [])

        assert "Failed" not in _statuses(writes)
        status, _, kw = writes[-1]
        assert status == "Stopping"
        assert kw["expected_status"] == "Stopping"
        assert kw["hyp_id"] == "hyp-1"
        assert [delay for delay, _, _ in timers] == [10]
        assert domain_guard.holder(DOMAIN)["operation"] == "destroy"

    def test_a_lookup_timeout_is_retried_too(self, env):
        writes, timers, _ = env
        w = _worker({"conn.lookupByName": _timeout("conn.lookupByName for stop")})

        w._handle_stop_domain(self.action(), 0.0, [])

        assert "Failed" not in _statuses(writes)
        assert len(timers) == 1

    def test_the_backoff_grows_and_settles_at_five_minutes(self, env):
        _, timers, _ = env
        w = _worker({"domain.destroy": _timeout("domain.destroy")})
        action = self.action()
        for _ in range(8):
            w._handle_stop_domain(action, 0.0, [])
            action = timers[-1][2][0]
        assert [d for d, _, _ in timers] == [10, 20, 40, 80, 160, 300, 300, 300]

    def test_no_new_call_is_queued_behind_the_hung_one(self, env):
        _, timers, _ = env
        hung = Future()
        w = _worker({"domain.destroy": _timeout("domain.destroy", hung)})
        w._handle_stop_domain(self.action(), 0.0, [])
        retry = timers[-1][2][0]
        w.executed.clear()

        w._handle_stop_domain(retry, 0.0, [])

        assert w.executed == []
        assert [d for d, _, _ in timers] == [10, 20]

    def test_a_late_destroy_settles_the_stop(self, env):
        writes, timers, _ = env
        hung = Future()
        w = _worker({"domain.destroy": _timeout("domain.destroy", hung)})
        w._handle_stop_domain(self.action(), 0.0, [])

        hung.set_result(0)
        late = _drain(w)
        assert len(late) == 1
        w._handle_stop_domain(late[0], 0.0, [])

        status, _, kw = writes[-1]
        assert status == "Stopped"
        assert kw["expected_status"] == "Stopping"
        assert domain_guard.holder(DOMAIN) is None
        assert w._stop_retries == {}

    def test_a_settled_stop_ignores_its_pending_retries(self, env):
        writes, timers, _ = env
        hung = Future()
        w = _worker({"domain.destroy": _timeout("domain.destroy", hung)})
        w._handle_stop_domain(self.action(), 0.0, [])
        hung.set_result(0)
        w._handle_stop_domain(_drain(w)[0], 0.0, [])
        count = len(writes)

        # the timer of the first attempt fires after the stop is settled
        w._handle_stop_domain(timers[0][2][0], 0.0, [])

        assert len(writes) == count

    def test_late_answers_never_multiply_the_retries(self, env):
        calls = {"domain.destroy": _timeout("domain.destroy", Future())}
        w = _worker(calls)
        action = self.action()
        for _ in range(4):
            # each hung destroy fails late, requeueing the stop on top of
            # the timer already armed for it
            w._handle_stop_domain(action, 0.0, [])
            calls["domain.destroy"].future.set_exception(libvirtError("busy"))
            calls["domain.destroy"] = _timeout("domain.destroy", Future())
            action = _drain(w)[-1]
        assert len([t for t in ARMED if not t.cancelled]) == 1

    def test_any_other_error_still_fails(self, env):
        writes, _, _ = env
        error = libvirtError("boom")
        w = _worker({"domain.destroy": error})
        w._handle_stop_domain(self.action(), 0.0, [])
        assert _statuses(writes)[-1] == "Failed"
        assert domain_guard.holder(DOMAIN) is None


class TestOtherTimeouts:
    def test_a_reset_timeout_goes_back_to_started(self, env):
        writes, _, _ = env
        w = _worker({"domain.reset": _timeout("domain.reset")})
        w._handle_reset_domain({"type": "reset_domain", "id_domain": DOMAIN}, 0.0, [])
        status, _, kw = writes[-1]
        assert status == "Started"
        assert kw["expected_status"] == "Resetting"

    def test_a_shutdown_timeout_writes_nothing(self, env):
        writes, _, _ = env
        w = _worker({"domain.shutdownFlags": _timeout("domain.shutdownFlags")})
        w._handle_shutdown_domain(
            {"type": "shutdown_domain", "id_domain": DOMAIN}, 0.0, []
        )
        assert writes == []


class TestLateCreate:
    def start(self):
        return {"type": "start_domain", "id_domain": DOMAIN, "xml": "<domain/>"}

    def paused(self):
        return {"type": "start_paused_domain", "id_domain": DOMAIN, "xml": "<x/>"}

    def test_a_create_timeout_is_not_a_failure(self, env):
        writes, _, status = env
        status["value"] = "Starting"
        w = _worker({"libvirt createXML": _timeout("libvirt createXML", Future())})

        w._handle_start_domain(self.start(), 0.0, [])

        assert writes == []
        assert domain_guard.holder(DOMAIN)["operation"] == "createXML"

    def test_a_late_create_is_adopted_with_its_viewer(self, env):
        writes, _, status = env
        status["value"] = "Starting"
        hung = Future()
        w = _worker({"libvirt createXML": _timeout("libvirt createXML", hung)})
        w._process_domain_startup = MagicMock()
        w._handle_start_domain(self.start(), 0.0, [])

        hung.set_result(MagicMock())
        late = _drain(w)
        w._process_action(late[0], 0.0, [])

        w._process_domain_startup.assert_called_once()
        assert domain_guard.holder(DOMAIN) is None

    def test_a_late_create_the_broom_already_adopted_still_gets_its_viewer(self, env):
        _, _, status = env
        status["value"] = "Starting"
        hung = Future()
        w = _worker({"libvirt createXML": _timeout("libvirt createXML", hung)})
        w._process_domain_startup = MagicMock()
        w._handle_start_domain(self.start(), 0.0, [])
        status["value"] = "Started"

        hung.set_result(MagicMock())
        w._process_action(_drain(w)[0], 0.0, [])

        w._process_domain_startup.assert_called_once()

    def test_a_late_create_nobody_wants_is_destroyed(self, env):
        writes, _, status = env
        status["value"] = "Starting"
        hung = Future()
        w = _worker({"libvirt createXML": _timeout("libvirt createXML", hung)})
        w._process_domain_startup = MagicMock()
        w._handle_start_domain(self.start(), 0.0, [])
        status["value"] = "Stopped"

        hung.set_result(MagicMock())
        w.executed.clear()
        w._process_action(_drain(w)[0], 0.0, [])

        w._process_domain_startup.assert_not_called()
        assert w.executed == ["libvirt domain.destroy() of a late create"]
        assert writes == []

    def test_a_late_create_error_fails_as_that_error(self, env):
        writes, _, status = env
        status["value"] = "Starting"
        hung = Future()
        w = _worker({"libvirt createXML": _timeout("libvirt createXML", hung)})
        w._handle_start_domain(self.start(), 0.0, [])

        hung.set_exception(libvirtError("cannot open disk"))
        w._process_action(_drain(w)[0], 0.0, [])

        status_written, _, kw = writes[-1]
        assert status_written == "Failed"
        assert "cannot open disk" in kw["detail"]

    def test_a_late_paused_test_domain_is_destroyed_and_the_test_passes(self, env):
        writes, _, status = env
        status["value"] = "StartingPaused"
        hung = Future()
        w = _worker(
            {"libvirt createXML paused": _timeout("libvirt createXML paused", hung)}
        )
        w._handle_start_paused_domain(self.paused(), 0.0, [])
        assert writes == []

        hung.set_result(MagicMock())
        w.executed.clear()
        w._process_action(_drain(w)[0], 0.0, [])

        assert w.executed == ["libvirt domain.destroy() of a late create"]
        status_written, _, kw = writes[-1]
        assert status_written == "Stopped"
        assert kw["expected_status"] == "StartingPaused"
        assert domain_guard.holder(DOMAIN) is None


class TestNeverTwice:
    def start(self):
        return {"type": "start_domain", "id_domain": DOMAIN, "xml": "<domain/>"}

    def test_a_domain_held_elsewhere_is_not_started(self, env):
        writes, _, _ = env
        domain_guard.hold(DOMAIN, "hyp-2", "destroy")
        w = _worker({})

        w._handle_start_domain(self.start(), 0.0, [])

        assert "libvirt createXML" not in w.executed
        status, _, kw = writes[-1]
        assert status == "Failed"
        assert "hyp-2" in kw["detail"]

    def test_a_paused_test_is_refused_too(self, env):
        domain_guard.hold(DOMAIN, "hyp-2", "createXML")
        w = _worker({})
        w._handle_start_paused_domain(
            {"type": "start_paused_domain", "id_domain": DOMAIN, "xml": "<x/>"},
            0.0,
            [],
        )
        assert w.executed == []

    def test_once_the_stop_settles_it_starts(self, env):
        _, _, status = env
        hung = Future()
        stopper = _worker({"domain.destroy": _timeout("domain.destroy", hung)})
        stopper._handle_stop_domain(
            {"type": "stop_domain", "id_domain": DOMAIN}, 0.0, []
        )
        starter = _worker({})
        starter.hyp_id = "hyp-2"
        starter._process_domain_startup = MagicMock()
        starter._handle_start_domain(self.start(), 0.0, [])
        assert "libvirt createXML" not in starter.executed

        hung.set_result(0)
        stopper._handle_stop_domain(_drain(stopper)[0], 0.0, [])
        starter._handle_start_domain(self.start(), 0.0, [])

        assert "libvirt createXML" in starter.executed
