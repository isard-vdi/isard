"""Subscription lifecycle of the libvirt event collector, driven through the real run() loop."""

import inspect
import queue
import sys
import threading
import time
from unittest.mock import MagicMock

import libvirt
import pytest

# conftest's rethinkdb stub is not a package: lift it for this import only
_rethinkdb_stubs = {
    name: sys.modules.pop(name)
    for name in list(sys.modules)
    if name == "rethinkdb" or name.startswith("rethinkdb.")
}
try:
    import engine.controllers.events_recolector as er
finally:
    sys.modules.update(_rethinkdb_stubs)

# a star-import over conftest's MagicMock brings no names: supply the two the module uses
for _name in ("log", "logs"):
    if not hasattr(er, _name):
        setattr(er, _name, MagicMock(name=f"events_recolector.{_name}"))


DOM = "d9cf9dc9-841c-4bdc-996d-945c675b81f5"
HYP = "hyp1"
HYP2 = "hyp2"

# one 1 s loop tick plus slack, once the running fixture has zeroed the backoffs
RESUBSCRIBE_DEADLINE = 6.0

# must cover a full idle tick, or a negative assertion passes while the loop sleeps
SETTLE = 1.5


class _Queue:
    """A real PriorityQueueIsard: conftest mocks it, and FIFO between equal priorities matters here."""

    def __init__(self):
        self._q = queue.PriorityQueue()
        self.counter = 0

    def put(self, item, priority=100, block=True, timeout=None):
        self.counter += 1
        self._q.put((priority, self.counter, item), block=block, timeout=timeout)

    def get(self, block=True, timeout=None):
        return self._q.get(block=block, timeout=timeout)[-1]


class _NativeLoop:
    """Stand-in for the native event loop thread, which would spin on a stubbed libvirt."""

    def __init__(self, stop):
        self._stop = stop

    def is_alive(self):
        return self._stop[0] is False

    def join(self, timeout=None):
        return None


class _Libvirt:
    """Records every openReadOnly, can break them, and refuses a second close callback like libvirt."""

    def __init__(self):
        self.conns = []
        self.uris = []
        self.threads = []
        self.fail_open = False
        self.fail_register = False

    def open(self, uri):
        self.uris.append(uri)
        self.threads.append(threading.current_thread())
        if self.fail_open:
            # What libvirt raises when the daemon is not there.
            raise libvirt.libvirtError("Cannot open {}".format(uri))
        conn = MagicMock(name="conn{}".format(len(self.conns)))
        conn.getURI.return_value = uri
        conn.getHostname.return_value = uri.split("@")[1].split(":")[0]
        conn.registerCloseCallback.side_effect = _close_callback_registrar()
        if self.fail_register:
            conn.domainEventRegisterAny.side_effect = libvirt.libvirtError(
                "internal error: client socket is closed"
            )
        self.conns.append(conn)
        return conn


def _close_callback_registrar():
    """libvirt allows exactly one close callback per connection."""
    registered = []

    def _register(callback, opaque):
        if registered:
            raise libvirt.libvirtError("A close callback is already registered")
        registered.append((callback, opaque))

    return _register


def _collector():
    return er.ThreadHypEvents(name="hyps_events_test")


# register_events gained hyp_id; bridged so the old signature fails at an assertion
_REGISTER_TAKES_HYP_ID = (
    len(inspect.signature(er.ThreadHypEvents.register_events).parameters) > 2
)


def _register_events(t, conn, hyp_id=HYP):
    if _REGISTER_TAKES_HYP_ID:
        return t.register_events(conn, hyp_id)
    return t.register_events(conn)


def _close_callback_of(conn):
    """The callback and the opaque the collector itself registered."""
    assert conn.registerCloseCallback.called, (
        "register_events did not register a close callback: there is no hook "
        "for F1 at all"
    )
    args = conn.registerCloseCallback.call_args.args
    return args[0], (args[1] if len(args) > 1 else None)


def _subscription_report(t):
    """The collector's own report of which hypervisors it is delivering events for."""
    for name in ("subscription_report", "subscription_status"):
        fn = getattr(t, name, None)
        if callable(fn):
            return fn()
    pytest.fail(
        "the collector cannot be asked what it is subscribed to: neither "
        "subscription_report() nor subscription_status() exists. That is F5 -- "
        "a live thread holding no subscriptions is the state no probe sees."
    )


def _report_sets(t):
    """(subscribed, down) as sets of hyp ids, from either report shape."""
    report = _subscription_report(t)
    assert isinstance(report, dict), "the subscription report must be a dict"
    if "subscribed" in report:
        subscribed = set(report.get("subscribed") or ())
        down = set(report.get("events_down") or ()) | set(report.get("failed") or ())
        return subscribed, down
    subscribed = {h for h, d in report.items() if d.get("subscribed")}
    return subscribed, set(report) - subscribed


def _wait_for(predicate, what, deadline=RESUBSCRIBE_DEADLINE):
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.02)
    pytest.fail("waited {}s for {} and it never happened".format(deadline, what))


@pytest.fixture
def virt(monkeypatch):
    """libvirt and the hypervisor rows, replaced. Yields the recorder."""
    double = _Libvirt()
    rows = {
        HYP: {"hostname": "hyp1.example", "user": "root", "port": 2022},
        HYP2: {"hostname": "hyp2.example", "user": "root", "port": 2022},
    }
    # returns False, not {}, for a row that is gone or lacks user/port
    monkeypatch.setattr(
        er, "get_hyp_hostname_user_port_from_id", lambda hyp_id: rows.get(hyp_id, False)
    )
    monkeypatch.setattr(
        er,
        "hostname_to_uri",
        lambda hostname, user, port: "qemu+ssh://{}@{}:{}/system".format(
            user, hostname, port
        ),
    )
    monkeypatch.setattr(er, "update_uri_hyp", MagicMock())
    monkeypatch.setattr(er.libvirt, "openReadOnly", double.open)
    return double


@pytest.fixture
def collector(virt):
    """A collector with a real queue, NOT running. For the pure functions."""
    t = _collector()
    t.q_event_register = _Queue()
    return t


@pytest.fixture
def running(collector, virt, monkeypatch):
    """The same collector with ``run()`` actually turning, in its own thread."""
    monkeypatch.setattr(er, "virEventLoopNativeStart", _NativeLoop)
    # zeroed so a retry fires on the next tick; raising=False as a design may lack one
    for name, value in (
        ("SLEEP_BETWEEN_TRY_REGISTER_EVENTS", 0),
        ("REGISTER_RETRY_SECONDS", 0),
        ("REGISTER_RETRY_MAX_SECONDS", 0),
        ("SUBSCRIBE_RETRY_BACKOFF", (0,)),
        ("EVENTS_RETRY_BACKOFF_SECONDS", (0,)),
    ):
        monkeypatch.setattr(er, name, value, raising=False)
    collector.daemon = True
    collector.start()
    yield collector
    # the action wakes the loop out of its queue wait; the flag is what stops it
    collector.stop = True
    collector.q_event_register.put({"type": "stop_thread"})
    collector.join(timeout=5)


def _subscribe(t, virt, hyp_id=HYP):
    """Register a hypervisor the way the worker thread does, and wait for it."""
    t.q_event_register.put(
        {"type": "add_hyp_to_receive_events", "hyp_id": hyp_id, "worker": MagicMock()}
    )
    _wait_for(lambda: hyp_id in t.hyps_conn, "{} to be subscribed".format(hyp_id))
    return t.hyps_conn[hyp_id]


# deregistering must never take the registration thread down


@pytest.mark.parametrize(
    "holds",
    [
        pytest.param(("conn",), id="conn-only-the-measured-F5-state"),
        pytest.param(("conn", "ids"), id="conn-and-ids"),
        pytest.param(("ids",), id="ids-only"),
        pytest.param(("hostname",), id="hostname-only"),
        pytest.param((), id="nothing"),
        pytest.param(("conn", "ids", "hostname"), id="complete"),
    ],
)
def test_del_hyp_leaves_nothing_behind_whatever_the_dicts_hold(collector, holds):
    """Deregistering clears every half-state a failed registration leaves, and never raises."""
    if "conn" in holds:
        collector.hyps_conn[HYP] = MagicMock()
    if "ids" in holds:
        collector.events_ids[HYP] = {"VIR_DOMAIN_EVENT_ID_LIFECYCLE": 0}
    if "hostname" in holds:
        collector.hyps[HYP] = "hyp1.example"

    collector.del_hyp_to_receive_events(HYP)

    assert (collector.hyps_conn, collector.events_ids, collector.hyps) == ({}, {}, {})


def test_del_hyp_forgets_the_worker_thread(collector):
    """Deregistering pops hyps_workers, and a second del_ must not raise."""
    collector.hyps_conn[HYP] = MagicMock()
    collector.events_ids[HYP] = {"VIR_DOMAIN_EVENT_ID_LIFECYCLE": 0}
    collector.hyps[HYP] = "hyp1.example"
    collector.hyps_workers[HYP] = MagicMock()

    collector.del_hyp_to_receive_events(HYP)
    collector.del_hyp_to_receive_events(HYP)

    assert collector.hyps_workers == {}


def test_del_hyp_closes_the_connection_and_deregisters_its_callbacks(collector):
    """Control: deregistering closes the connection and deregisters its callbacks."""
    conn = MagicMock()
    cb_ids = {"VIR_DOMAIN_EVENT_ID_LIFECYCLE": 0}
    collector.hyps_conn[HYP] = conn
    collector.events_ids[HYP] = cb_ids
    collector.hyps[HYP] = "hyp1.example"
    collector.unregister_events = MagicMock()

    collector.del_hyp_to_receive_events(HYP)

    collector.unregister_events.assert_called_once_with(conn, cb_ids)
    conn.close.assert_called_once()


# one bad action must not take the registration thread down


def test_a_poisoned_action_does_not_kill_the_registration_loop(running, virt):
    """An action with no type is logged and the loop keeps registering."""
    running.q_event_register.put({"broken_no_type_key": True})

    _subscribe(running, virt)

    assert running.is_alive()


def test_a_deregistration_queued_behind_a_poisoned_action_still_happens(running, virt):
    """A del_ queued behind a poisoned action is still processed."""
    conn = _subscribe(running, virt)

    running.q_event_register.put({"type": "add_hyp_to_receive_events"})
    running.q_event_register.put({"type": "del_hyp_to_receive_events", "hyp_id": HYP})

    _wait_for(lambda: HYP not in running.hyps_conn, "the queued del_ to be read")
    conn.close.assert_called_once()


def test_an_add_for_a_hypervisor_that_left_the_database_does_not_kill_the_loop(
    running, virt
):
    """A hypervisor row gone before its add is read must not kill the loop."""
    running.q_event_register.put(
        {
            "type": "add_hyp_to_receive_events",
            "hyp_id": "deleted-hypervisor",
            "worker": MagicMock(),
        }
    )

    _subscribe(running, virt)

    assert running.is_alive()
    assert "deleted-hypervisor" not in running.hyps_conn


# a dropped connection is re-subscribed


@pytest.mark.parametrize(
    "reason",
    [
        pytest.param(0, id="Error"),
        pytest.param(1, id="End-of-file"),
        pytest.param(2, id="Keepalive"),
        pytest.param(3, id="Client"),
    ],
)
def test_a_dropped_connection_is_re_subscribed_without_anyone_asking(
    running, virt, reason
):
    """A close callback for a subscription we did not retire re-subscribes, whatever the reason."""
    conn = _subscribe(running, virt)
    callback, opaque = _close_callback_of(conn)
    opened = len(virt.conns)

    callback(conn, reason, opaque)

    _wait_for(
        lambda: len(virt.conns) > opened,
        "a new connection for {} after reason={}".format(HYP, reason),
    )
    assert running.is_alive()


def test_a_close_callback_for_a_deregistered_hypervisor_resurrects_nothing(
    running, virt
):
    """A hypervisor we deregistered is not re-subscribed by its own close callback."""
    conn = _subscribe(running, virt)
    callback, opaque = _close_callback_of(conn)

    running.q_event_register.put({"type": "del_hyp_to_receive_events", "hyp_id": HYP})
    _wait_for(lambda: HYP not in running.hyps_conn, "the del_ to be read")
    opened = len(virt.conns)

    callback(conn, 3, opaque)  # VIR_CONNECT_CLOSE_REASON_CLIENT
    time.sleep(SETTLE)

    assert len(virt.conns) == opened
    assert HYP not in running.hyps_conn


@pytest.mark.parametrize(
    "reason",
    [
        pytest.param(4, id="one-past-the-end"),
        pytest.param(None, id="not-a-number"),
        pytest.param("End-of-file", id="a-string"),
    ],
)
def test_the_close_callback_never_raises_on_a_reason_it_does_not_know(
    collector, virt, reason
):
    """The close callback runs on libvirt's dispatch thread and must survive an unknown reason."""
    conn = virt.open("qemu+ssh://root@hyp1.example:2022/system")
    _register_events(collector, conn, HYP)
    callback, opaque = _close_callback_of(conn)

    callback(conn, reason, opaque)  # must not raise


# a retry registers on a fresh connection, never on the half-registered one


def test_every_registration_attempt_gets_a_connection_of_its_own(running, virt):
    """A failed registration discards its connection so the retry starts clean."""
    virt.fail_register = True

    running.q_event_register.put(
        {"type": "add_hyp_to_receive_events", "hyp_id": HYP, "worker": MagicMock()}
    )

    _wait_for(lambda: len(virt.conns) >= 2, "a second attempt on a second connection")
    assert virt.conns[0] is not virt.conns[1]
    virt.conns[0].close.assert_called_once()


def test_a_second_subscription_replaces_the_first_and_disposes_of_it(running, virt):
    """A double add must not leak the connection it replaces."""
    first = _subscribe(running, virt)

    running.q_event_register.put(
        {"type": "add_hyp_to_receive_events", "hyp_id": HYP, "worker": MagicMock()}
    )
    _wait_for(
        lambda: running.hyps_conn.get(HYP) not in (None, first),
        "the second subscription to be installed",
    )

    assert running.hyps_conn[HYP] is virt.conns[-1]
    first.close.assert_called_once()
    assert len(running.hyps_conn) == 1


@pytest.mark.parametrize(
    "break_at",
    [
        pytest.param("open", id="openReadOnly-fails"),
        pytest.param("register", id="register_events-fails"),
    ],
)
def test_a_failed_re_subscription_keeps_the_one_that_still_delivers(
    running, virt, break_at
):
    """The old subscription is retired only after its replacement registers."""
    first = _subscribe(running, virt)
    setattr(virt, "fail_" + break_at, True)
    attempts = len(virt.uris)

    running.q_event_register.put(
        {"type": "add_hyp_to_receive_events", "hyp_id": HYP, "worker": MagicMock()}
    )
    _wait_for(lambda: len(virt.uris) > attempts, "the failing attempt to be made")
    time.sleep(SETTLE)

    assert running.hyps_conn[HYP] is first
    assert running.events_ids.get(HYP)
    first.close.assert_not_called()


# the handshake runs off the registration loop


def test_the_ssh_handshake_does_not_run_on_the_registration_loop(running, virt):
    """openReadOnly runs on the hypervisor's timeout executor, not on the registration loop."""
    _subscribe(running, virt)

    assert virt.threads, "openReadOnly was never called"
    assert running not in virt.threads, (
        "openReadOnly ran on the registration loop itself: an unreachable "
        "hypervisor blocks every other hypervisor's subscription"
    )
    assert all(
        t.name.startswith("libvirt_timeout_") for t in virt.threads
    ), "the handshake is off the loop but not on services/lib/libvirt_timeout.py"


# a failed subscription keeps being retried


@pytest.mark.parametrize(
    "break_at",
    [
        pytest.param("open", id="openReadOnly-fails-once"),
        pytest.param("register", id="register_events-fails-once"),
    ],
)
def test_a_subscription_that_failed_is_retried_by_the_collector_itself(
    running, virt, break_at
):
    """After a failed subscription the collector itself retries once the fault clears."""
    setattr(virt, "fail_" + break_at, True)

    running.q_event_register.put(
        {"type": "add_hyp_to_receive_events", "hyp_id": HYP, "worker": MagicMock()}
    )
    _wait_for(
        lambda: len(virt.uris) >= 1, "the first attempt", deadline=RESUBSCRIBE_DEADLINE
    )
    setattr(virt, "fail_" + break_at, False)

    _wait_for(lambda: HYP in running.hyps_conn, "the subscription to be rebuilt")
    assert running.is_alive()


def test_a_hypervisor_that_never_comes_back_is_still_being_retried(running, virt):
    """Repeated failures keep the collector retrying and reporting the hypervisor down."""
    er.logs.reset_mock()
    virt.fail_open = True

    running.q_event_register.put(
        {"type": "add_hyp_to_receive_events", "hyp_id": HYP, "worker": MagicMock()}
    )

    _wait_for(lambda: len(virt.uris) >= 3, "a third attempt")
    assert running.is_alive()
    assert er.logs.status.error.called or er.logs.status.warning.called, (
        "a hypervisor receiving no events must be visible at a level this "
        "engine actually emits: measured, 187+51 logs.*.debug() call sites "
        "produce 0 DEBUG lines against 333 INFO in half an hour, because "
        "isardvdi_common/helpers/log.py:71-75 resets the root logger"
    )


def test_a_hypervisor_that_is_not_in_the_database_is_not_retried_for_ever(
    running, virt
):
    """Control: with no hypervisor row there is nothing to retry."""
    running.q_event_register.put(
        {
            "type": "add_hyp_to_receive_events",
            "hyp_id": "deleted-hypervisor",
            "worker": MagicMock(),
        }
    )
    time.sleep(SETTLE)
    attempts = len(virt.uris)
    time.sleep(SETTLE)

    assert len(virt.uris) == attempts
    assert running.is_alive()


# the subscription report


def test_the_collector_says_which_hypervisors_it_is_delivering_for(running, virt):
    """The report lists every subscribed hypervisor and none down."""
    _subscribe(running, virt, HYP)
    _subscribe(running, virt, HYP2)

    subscribed, down = _report_sets(running)

    assert subscribed == {HYP, HYP2}
    assert down == set()


def test_a_hypervisor_with_no_subscription_is_reported_down_by_a_live_thread(
    running, virt
):
    """A dropped connection is reported down while the thread is alive."""
    conn = _subscribe(running, virt)
    callback, opaque = _close_callback_of(conn)
    virt.fail_open = True

    callback(conn, 1, opaque)  # End-of-file, the reason measured live

    _wait_for(lambda: HYP in _report_sets(running)[1], "{} reported down".format(HYP))
    subscribed, down = _report_sets(running)
    assert HYP not in subscribed, (
        "the hypervisor is reported as subscribed AND as down at the same "
        "time. The rule anyone writes against this report is 'Online and not "
        "in subscribed', and a connection kept in hyps_conn because it MIGHT "
        "still deliver keeps that rule quiet -- which is F5 again, with a new "
        "name. What the report answers has to be 'am I delivering for this "
        "hypervisor', not 'do I hold an object for it'"
    )
    assert running.is_alive()


def test_a_deregistered_hypervisor_leaves_the_report(running, virt):
    """Control: a deregistered hypervisor leaves the report instead of staying down."""
    _subscribe(running, virt)

    running.q_event_register.put({"type": "del_hyp_to_receive_events", "hyp_id": HYP})
    _wait_for(lambda: HYP not in running.hyps_conn, "the del_ to be read")

    subscribed, down = _report_sets(running)
    assert HYP not in subscribed
    assert HYP not in down


# mutations the characterisation tests do not see


def test_events_of_two_domains_are_processed_at_the_same_time():
    """One slow write must not hold up other domains' events: the pool needs more than one worker."""
    barrier = threading.Barrier(2)
    entered = []

    def _slow(*args, **kwargs):
        entered.append(threading.current_thread())
        barrier.wait(timeout=5)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(er, "_process_domain_event_async", _slow)
        conn = MagicMock()
        conn.getURI.return_value = "qemu+ssh://root@hyp1.example:2022/system"
        dom, other = MagicMock(), MagicMock()
        dom.name.return_value = DOM
        other.name.return_value = DOM + "-other"

        er.myDomainEventCallbackRethink(conn, dom, 2, 0, None)
        er.myDomainEventCallbackRethink(conn, other, 5, 1, None)

        _wait_for(lambda: len(entered) == 2, "both events to be in flight at once")

    assert len(set(entered)) == 2


@pytest.mark.parametrize(
    "status",
    ["Started", "Starting", "Paused", "Failed", "Unknown", "Shutting-down"],
)
def test_stopped_is_honoured_for_every_status_but_the_two_that_are_excluded(
    monkeypatch, status
):
    """Only Stopped and ForceDeleting are excluded; any other status takes a Stopped event."""
    ns = MagicMock()
    monkeypatch.setattr(er, "get_id_hyp_from_uri", lambda uri: HYP)
    monkeypatch.setattr(
        er, "get_domain_hyp_started_and_status_and_detail", ns.get_domain
    )
    monkeypatch.setattr(er, "update_domain_status", ns.update_domain_status)
    monkeypatch.setattr(er, "update_vgpu_info_if_stopped", ns.update_vgpu)
    ns.get_domain.return_value = {"status": status, "hyp_started": HYP}

    er._process_domain_event_async(
        "qemu+ssh://root@hyp1.example:2022/system", DOM, 5, 1, None, 1788600000
    )

    assert ns.update_domain_status.call_args.kwargs["status"] == "Stopped"


def test_the_graphics_callback_pays_for_an_rpc_on_the_libvirt_loop_thread():
    """WRONG ON PURPOSE: getHostname is an RPC on the libvirt loop thread where getURI would do."""
    conn = MagicMock()
    conn.getHostname.return_value = "hyp1.example"
    dom = MagicMock()
    dom.name.return_value = DOM
    addr = {"node": "192.0.2.1", "service": "5900"}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(er, "_process_graphics_event_async", MagicMock())
        er.myDomainEventGraphicsCallbackRethink(
            conn, dom, 0, addr, addr, "none", None, None
        )

    conn.getHostname.assert_called_once()
    conn.getURI.assert_not_called()
