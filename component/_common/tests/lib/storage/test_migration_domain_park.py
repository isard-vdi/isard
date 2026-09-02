# SPDX-License-Identifier: AGPL-3.0-or-later

"""The disk's domains follow it into maintenance while it is being moved.

Pins the two halves that make the park safe: the ledger records WHICH domains
were parked before any status is written, and the restore only takes back a
domain still sitting in ``Maintenance``.
"""

import isardvdi_common.lib.storage.migration_run as mr


class _D:
    """A domain that records every status write into a shared trace."""

    def __init__(self, did, status, trace=None):
        object.__setattr__(self, "_trace", trace if trace is not None else [])
        self.id = did
        self.status = status
        self.current_action = None

    def __setattr__(self, name, value):
        if name == "status":
            self._trace.append(("write", self.id, value))
        object.__setattr__(self, name, value)


def _runner(monkeypatch, item, domains):
    """A bare runner with only the collaborators these helpers use."""
    trace = []
    for domain in domains:
        object.__setattr__(domain, "_trace", trace)
    by_id = {domain.id: domain for domain in domains}

    runner = object.__new__(mr.MigrationRunner)

    def _set(it, **fields):
        trace.append(("ledger", dict(fields)))
        it.update(fields)

    runner._set = _set
    runner._domains = lambda storage_id: domains
    monkeypatch.setattr(mr, "Domain", lambda did: by_id[did])
    return runner, trace


# --------------------------------------------------------------------------- #
# park
# --------------------------------------------------------------------------- #
def test_park_takes_only_stopped_domains(monkeypatch):
    item = {"id": "i1", "storage_id": "s1"}
    stopped, running = _D("d1", "Stopped"), _D("d2", "Started")
    r, _ = _runner(monkeypatch, item, [stopped, running])
    r._park_domains(item)
    assert item["maintenance_domains"] == ["d1"]
    assert stopped.status == "Maintenance"
    assert stopped.current_action == "move"
    # a domain we do not own is never taken over
    assert running.status == "Started"


def test_park_records_the_ledger_before_it_writes(monkeypatch):
    """The ids must be durable BEFORE the statuses change: a crash in between
    would leave desktops in maintenance that nothing can find."""
    item = {"id": "i1", "storage_id": "s1"}
    r, trace = _runner(monkeypatch, item, [_D("d1", "Stopped")])
    r._park_domains(item)
    assert trace[0][0] == "ledger"
    assert trace[1] == ("write", "d1", "Maintenance")


def test_park_is_recorded_once_per_attempt(monkeypatch):
    """The empty list is a settled answer, so a second tick must not re-park."""
    item = {"id": "i1", "storage_id": "s1", "maintenance_domains": []}
    r, trace = _runner(monkeypatch, item, [_D("d1", "Stopped")])
    r._park_domains(item)
    assert trace == []


# --------------------------------------------------------------------------- #
# restore
# --------------------------------------------------------------------------- #
def test_restore_puts_the_parked_domains_back(monkeypatch):
    item = {"id": "i1", "storage_id": "s1", "maintenance_domains": ["d1"]}
    parked = _D("d1", "Maintenance")
    parked.current_action = "move"
    r, _ = _runner(monkeypatch, item, [parked])
    r._restore_domains(item)
    assert parked.status == "Stopped"
    assert parked.current_action is None


def test_restore_leaves_a_domain_that_moved_on(monkeypatch):
    """Whatever took it out of maintenance owns it now."""
    item = {"id": "i1", "storage_id": "s1", "maintenance_domains": ["d1"]}
    moved_on = _D("d1", "Started")
    r, _ = _runner(monkeypatch, item, [moved_on])
    r._restore_domains(item)
    assert moved_on.status == "Started"


def test_restore_runs_before_the_storage_original_early_return(monkeypatch):
    """A disk can carry parked domains and no recorded storage original; the
    early return for the storage status must not strand them."""
    item = {
        "id": "i1",
        "storage_id": "s1",
        "maintenance_domains": ["d1"],
        "storage_orig_status": None,
    }
    parked = _D("d1", "Maintenance")
    r, _ = _runner(monkeypatch, item, [parked])
    r._restore_storage_status(item)
    assert parked.status == "Stopped"
