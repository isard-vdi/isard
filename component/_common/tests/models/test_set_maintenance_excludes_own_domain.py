#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Josep Maria Viñolas Auquer
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deleting a running desktop's disk cannot require that desktop to be stopped.

The engine stops it with ``not_change_status``, on purpose, so the row never
reaches ``Stopped`` on that path. Requiring it refused every time, the refusal
was swallowed, and the desktop row was dropped with its qcow2 still on disk and
in no recycle bin.

The invariant still holds for everybody else: a *different* desktop running on
the same disk must still block it.
"""

from unittest.mock import PropertyMock, patch

import pytest
from isardvdi_common.models.storage import Storage


def _domain(store, domain_id, read_status):
    """A domain as the preconditions read it, over the row as it now is."""

    class _Domain:
        def __init__(self):
            object.__setattr__(self, "id", domain_id)

        @property
        def status(self):
            return read_status

        def __setattr__(self, name, value):
            store.setdefault(domain_id, {})[name] = value

    return _Domain()


def _storage(store, domain_statuses):
    """A Storage whose ``domains`` report the given id -> status."""
    storage = Storage.__new__(Storage)
    domains = [
        _domain(store, domain_id, status)
        for domain_id, status in domain_statuses.items()
    ]
    return storage, domains


def _guarded(store):
    """Honour the guarded write against ``store``, which is the live row."""

    def _update_document_if(
        doc_id,
        update_data,
        *,
        field=None,
        values=None,
        excluding=None,
        validate=True,
    ):
        row = store.get(doc_id, {})
        held = row.get(field)
        if field is not None and (
            (values is not None and held not in values)
            or (excluding is not None and held in excluding)
        ):
            return False
        store.setdefault(doc_id, {}).update(update_data)
        return True

    return _update_document_if


def _run(
    domain_statuses,
    exclude_domains=None,
    live_statuses=None,
    store=None,
    action="delete",
):
    """Run set_maintenance; ``live_statuses`` is what the rows hold when the writes land."""
    store = {} if store is None else store
    store["storage-1"] = {"status": "ready"}
    for domain_id, status in domain_statuses.items():
        store[domain_id] = {"status": status}
    store.update({k: {"status": v} for k, v in (live_statuses or {}).items()})

    storage, domains = _storage(store, domain_statuses)
    # ``Storage`` resolves its columns through ``__getattr__``, so they are set
    # on the instance rather than patched on the class.
    object.__setattr__(storage, "id", "storage-1")
    object.__setattr__(storage, "status", "ready")

    from isardvdi_common.models import domain as domain_module

    def _setattr(self, name, value):
        store.setdefault(self.id, {})[name] = value
        object.__setattr__(self, name, value)

    with patch.object(
        Storage, "domains", new_callable=PropertyMock, return_value=domains
    ), patch.object(
        Storage, "children", new_callable=PropertyMock, return_value=[]
    ), patch.object(
        Storage, "__setattr__", _setattr
    ), patch.object(
        Storage, "update_document_if", staticmethod(_guarded(store))
    ), patch.object(
        domain_module.Domain, "update_document_if", staticmethod(_guarded(store))
    ), patch.object(
        Storage, "_update_cache"
    ):
        storage.set_maintenance(action, exclude_domains=exclude_domains)
    return domains, store


def _code(raised):
    """The refusal's description code, whichever shape the exception has.

    On this branch ``set_maintenance`` still raises a plain ``Exception`` and
    the code is the third positional argument. `!5003` turns the whole model
    into a typed ``Error`` that carries it as ``description_code`` so apiv4
    answers 428 instead of a generic 500 — and then ``args[2]`` no longer
    exists. Asserting the code rather than its position keeps this test honest
    on both sides, which matters because neither branch can see the other.
    """
    err = raised.value
    code = getattr(err, "description_code", None)
    if code is None and isinstance(getattr(err, "error", None), dict):
        code = err.error.get("description_code")
    if code is None and len(err.args) > 2:
        code = err.args[2]
    return code


def test_the_desktop_being_deleted_does_not_block_its_own_disk():
    _domains, store = _run({"desktop-1": "Started"}, exclude_domains=["desktop-1"])
    # And it is still parked, so the row says a task owns it while it happens.
    assert store["desktop-1"]["status"] == "Maintenance"
    assert store["desktop-1"]["current_action"] == "delete"
    assert store["storage-1"]["status"] == "maintenance"


def test_a_desktop_that_starts_while_the_preconditions_run_still_blocks_it():
    """The read said Stopped; the row says Starting when the write lands."""
    with pytest.raises(Exception) as raised:
        _run({"desktop-1": "Stopped"}, live_statuses={"desktop-1": "Starting"})

    assert _code(raised) == "desktops_not_stopped"


def test_a_refused_flip_puts_the_storage_back():
    """The storage is closed first, so a refusal has to reopen it."""
    store = {}
    with pytest.raises(Exception):
        _run(
            {"desktop-1": "Stopped", "desktop-2": "Stopped"},
            live_statuses={"desktop-2": "Starting"},
            store=store,
        )

    assert store["storage-1"]["status"] == "ready"
    assert store["desktop-1"]["status"] == "Stopped"


def test_another_running_desktop_on_the_same_disk_still_blocks_it():
    with pytest.raises(Exception) as raised:
        _run(
            {"desktop-1": "Started", "desktop-2": "Started"},
            exclude_domains=["desktop-1"],
        )
    assert _code(raised) == "desktops_not_stopped"


def test_without_the_exclusion_a_running_desktop_still_blocks_it():
    """The default is unchanged for every other caller."""
    with pytest.raises(Exception) as raised:
        _run({"desktop-1": "Started"})
    assert _code(raised) == "desktops_not_stopped"


def test_an_action_without_a_domain_precondition_never_parks_a_running_desktop():
    store = {}
    with pytest.raises(Exception) as raised:
        _run({"desktop-1": "Started"}, store=store, action="migrate")
    assert _code(raised) == "storage_invalid_maintenance_action"
    assert store["desktop-1"]["status"] == "Started"
    assert store["storage-1"]["status"] == "ready"


def test_a_refused_flip_puts_each_desktop_back_to_the_status_it_had():
    store = {}
    with pytest.raises(Exception) as raised:
        _run(
            {"desktop-1": "Failed", "desktop-2": "Stopped"},
            live_statuses={"desktop-2": "Starting"},
            store=store,
            action="repair",
        )
    assert _code(raised) == "desktops_not_stopped"
    assert store["desktop-1"]["status"] == "Failed"
    assert store["storage-1"]["status"] == "ready"
