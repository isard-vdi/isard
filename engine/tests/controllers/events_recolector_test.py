"""Characterisation of the libvirt event collector; WRONG ON PURPOSE marks a pinned defect."""

import sys
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

# supply only the log names the module uses, so a missing one still fails
for _name in ("log", "logs"):
    if not hasattr(er, _name):
        setattr(er, _name, MagicMock(name=f"events_recolector.{_name}"))


URI = "qemu+ssh://root@hyp1:2022/system"
DOM = "d9cf9dc9-841c-4bdc-996d-945c675b81f5"
HYP = "hyp1"


@pytest.fixture
def db(monkeypatch):
    """The collector's DB surface, as mocks. Returns the namespace to assert on."""
    ns = MagicMock()
    monkeypatch.setattr(er, "get_id_hyp_from_uri", lambda uri: HYP)
    monkeypatch.setattr(
        er, "get_domain_hyp_started_and_status_and_detail", ns.get_domain
    )
    monkeypatch.setattr(er, "update_domain_status", ns.update_domain_status)
    monkeypatch.setattr(er, "update_vgpu_info_if_stopped", ns.update_vgpu)
    return ns


def _fire(db, event, detail, status, hyp_started=HYP):
    """Feed one lifecycle event to the collector against a given DB row."""
    db.get_domain.return_value = {"status": status, "hyp_started": hyp_started}
    er._process_domain_event_async(URI, DOM, event, detail, None, 1788600000)


# domDetailToString

# transcribed, not read from the module, so editing DOM_EVENTS fails here
EXPECTED_DETAILS = {
    0: ("Added", "Updated", "Renamed", "Snapshot"),
    1: ("Removed", "Renamed"),
    2: ("Booted", "Migrated", "Restored", "Snapshot", "Wakeup"),
    3: (
        "Paused",
        "Migrated",
        "IOError",
        "Watchdog",
        "Restored",
        "Snapshot",
        "API error",
        "Postcopy",
        "Postcopy failed",
    ),
    4: ("Unpaused", "Migrated", "Snapshot", "Postcopy"),
    5: (
        "Shutdown",
        "Destroyed",
        "Crashed",
        "Migrated",
        "Saved",
        "Failed",
        "Snapshot",
        "Daemon",
    ),
    6: ("Finished", "On guest request", "On host request"),
    7: ("Memory", "Disk"),
    8: ("Panicked",),
}


@pytest.mark.parametrize(
    "event,detail,expected",
    [
        (e, d, name)
        for e, names in EXPECTED_DETAILS.items()
        for d, name in enumerate(names)
    ],
)
def test_dom_detail_to_string_every_valid_index(event, detail, expected):
    assert er.domDetailToString(event, detail) == expected


@pytest.mark.parametrize(
    "event,detail",
    [
        (5, 8),  # one past the end of Stopped
        (9, 0),  # no such event
        (2, 99),  # detail far out of range
    ],
)
def test_dom_detail_to_string_out_of_range_returns_placeholder(event, detail):
    """Out of range is swallowed and reported, not raised."""
    er.logs.reset_mock()

    assert er.domDetailToString(event, detail) == "Detail undefined"
    assert er.logs.status.error.called


@pytest.mark.parametrize(
    "event,detail,wrong_answer",
    [
        (-1, 0, "Panicked"),  # DOM_EVENTS[-1] is Crashed
        (5, -1, "Daemon"),  # Stopped's LAST detail, not an error
        (-5, -1, "Postcopy"),  # Resumed's last, from two negatives
    ],
)
def test_dom_detail_negative_indexes_wrap_silently(event, detail, wrong_answer):
    """WRONG ON PURPOSE: a negative index returns a wrong label instead of Detail undefined."""
    er.logs.reset_mock()

    assert er.domDetailToString(event, detail) == wrong_answer
    assert not er.logs.status.error.called  # no complaint at all


def test_dom_detail_stopped_7_says_daemon():
    """WRONG ON PURPOSE: Stopped[7] is labelled Daemon; libvirt >= 11.6.0 calls it Recreated."""
    assert libvirt.VIR_DOMAIN_EVENT_STOPPED_RECREATED == 7
    assert er.domDetailToString(5, 7) == "Daemon"


@pytest.mark.parametrize(
    "event,detail,libvirt_const",
    [
        (2, 5, "VIR_DOMAIN_EVENT_STARTED_RECREATED"),
        (3, 9, "VIR_DOMAIN_EVENT_SUSPENDED_GUEST_SHUTDOWN"),
        (4, 4, "VIR_DOMAIN_EVENT_RESUMED_POSTCOPY_FAILED"),
        (8, 1, "VIR_DOMAIN_EVENT_CRASHED_CRASHLOADED"),
    ],
)
def test_dom_detail_missing_indexes_degrade_loudly(event, detail, libvirt_const):
    """WRONG ON PURPOSE: details DOM_EVENTS lacks take the except instead of their libvirt name."""
    assert getattr(libvirt, libvirt_const) == detail
    assert er.domDetailToString(event, detail) == "Detail undefined"


# domEventToString has no try


def test_dom_event_to_string_every_valid_index():
    assert [er.domEventToString(i) for i in range(9)] == [
        "Defined",
        "Undefined",
        "Started",
        "Suspended",
        "Resumed",
        "Stopped",
        "Shutdown",
        "PMSuspended",
        "Crashed",
    ]


def test_dom_event_to_string_out_of_range_raises():
    """WRONG ON PURPOSE: an unknown event type raises IndexError instead of degrading."""
    with pytest.raises(IndexError):
        er.domEventToString(9)


def test_dom_event_to_string_negative_index_wraps_silently():
    """Negative indexes are valid Python and return the WRONG name silently."""
    assert er.domEventToString(-1) == "Crashed"


# the two early exits of _process_domain_event_async


def test_domain_not_in_database_writes_nothing(db):
    """A row that is gone (``{}``) is dropped before any decision is taken."""
    _fire(db, 2, 0, status=None)
    db.get_domain.return_value = {}
    er._process_domain_event_async(URI, DOM, 2, 0, None, 1788600000)

    db.update_domain_status.assert_not_called()


def test_event_from_a_different_hypervisor_writes_nothing(db):
    """The guard added in 692b68b2b: the domain runs somewhere else."""
    _fire(db, 5, 1, status="Started", hyp_started="a-different-hypervisor")

    db.update_domain_status.assert_not_called()
    assert er.logs.status.warning.called


@pytest.mark.parametrize("hyp_started", [None, "", False])
def test_hypervisor_guard_is_skipped_when_hyp_started_is_unset(db, hyp_started):
    """None/""/False all mean "not started anywhere", so the event is honoured."""
    _fire(db, 5, 1, status="Started", hyp_started=hyp_started)

    db.update_domain_status.assert_called_once()


# F-EXTRA: the guard chain falls through and writes a non-status


def test_resumed_over_failed_writes_nothing(db):
    """F-EXTRA: a lifecycle event no longer revives a Failed or Stopped row."""
    _fire(db, 4, 0, status="Failed")  # Resumed(Unpaused) over Failed

    db.update_domain_status.assert_not_called()


def test_the_same_event_over_stopped_writes_nothing(db):
    """The control for the test above: only the previous status differs."""
    _fire(db, 4, 0, status="Stopped")  # Resumed(Unpaused) over Stopped

    db.update_domain_status.assert_not_called()


# every branch of the Started/Resumed guard chain


@pytest.mark.parametrize(
    "status,event,detail",
    [
        ("StartingDomainDisposable", 4, 0),  # Resumed
        ("CreatingDomain", 2, 0),  # Started
        ("Stopped", 4, 0),  # Resumed
        ("Started", 4, 0),  # Resumed
        ("Starting", 4, 0),  # Resumed
    ],
)
def test_guarded_combinations_write_nothing(db, status, event, detail):
    """The five (previous status, event) pairs the chain deliberately swallows."""
    _fire(db, event, detail, status=status)

    db.update_domain_status.assert_not_called()


def test_unpaused_over_paused_is_translated_to_started(db):
    """The one branch that maps the event to a real status instead of copying it."""
    _fire(db, 4, 0, status="Paused")  # Resumed(Unpaused) over Paused

    kwargs = db.update_domain_status.call_args.kwargs
    assert kwargs["status"] == "Started"
    assert kwargs["detail"] == "Event received: Unpaused"


def test_started_booted_over_starting_writes_started(db):
    """The ordinary happy path: the start that raised the event is still on the row."""
    _fire(db, 2, 0, status="Starting")  # Started(Booted)

    kwargs = db.update_domain_status.call_args.kwargs
    assert kwargs["status"] == "Started"
    assert kwargs["detail"] == "Event received: Booted"
    assert kwargs["hyp_id"] == HYP


@pytest.mark.parametrize("status", ["Failed", "Stopped"])
@pytest.mark.parametrize("event,detail", [(2, 0), (3, 0), (4, 0)])
def test_a_late_event_does_not_revive_a_settled_row(db, status, event, detail):
    """A Booted, Suspended or Resumed raised before the row was settled must not
    undo it; whether the domain really runs is the broom's live listing to say."""
    _fire(db, event, detail, status=status)

    db.update_domain_status.assert_not_called()


def test_started_over_creating_domain_is_swallowed_but_resumed_is_not(db):
    """WRONG ON PURPOSE: Resumed over CreatingDomain writes status Resumed, unlike Started."""
    _fire(db, 2, 0, status="CreatingDomain")  # Started -> guarded
    db.update_domain_status.assert_not_called()

    _fire(db, 4, 0, status="CreatingDomain")  # Resumed -> falls through
    assert db.update_domain_status.call_args.kwargs["status"] == "Resumed"


# Stopped over ForceDeleting


def test_stopped_over_force_deleting_skips_the_write_but_still_frees_the_vgpu(db):
    _fire(db, 5, 1, status="ForceDeleting")  # Stopped(Destroyed)

    db.update_domain_status.assert_not_called()
    db.update_vgpu.assert_called_once_with(DOM)


def test_stopped_over_started_writes_and_frees_the_vgpu(db):
    """Control for the above: same event, unguarded status."""
    _fire(db, 5, 1, status="Started")

    kwargs = db.update_domain_status.call_args.kwargs
    assert kwargs["status"] == "Stopped"
    assert kwargs["detail"] == "Ready to Start"
    assert kwargs["hyp_id"] is False
    db.update_vgpu.assert_called_once_with(DOM)


def test_stopped_over_stopped_writes_nothing_but_still_frees_the_vgpu(db):
    _fire(db, 5, 1, status="Stopped")

    db.update_domain_status.assert_not_called()
    db.update_vgpu.assert_called_once_with(DOM)


# del_hyp_to_receive_events


def _collector():
    return er.ThreadHypEvents(name="hyps_events_test")


def test_del_hyp_on_coherent_state_cleans_all_three_dicts():
    """Control: with the state the happy path leaves, del_ is clean."""
    t = _collector()
    conn = MagicMock()
    t.hyps_conn[HYP] = conn
    t.events_ids[HYP] = {"VIR_DOMAIN_EVENT_ID_LIFECYCLE": 0}
    t.hyps[HYP] = "hyp1.example"

    t.del_hyp_to_receive_events(HYP)

    assert (t.hyps_conn, t.events_ids, t.hyps) == ({}, {}, {})
    conn.close.assert_called_once()


def test_del_hyp_for_an_unknown_hypervisor_is_a_no_op():
    """The hyps_conn guard keeps a failed openReadOnly harmless."""
    t = _collector()

    t.del_hyp_to_receive_events("never-registered")  # must not raise
