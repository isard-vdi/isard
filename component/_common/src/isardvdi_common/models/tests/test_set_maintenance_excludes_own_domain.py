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

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from isardvdi_common.models.storage import Storage


def _storage(domain_statuses):
    """A Storage whose ``domains`` are mocks with the given id -> status."""
    storage = Storage.__new__(Storage)
    domains = []
    for domain_id, status in domain_statuses.items():
        domain = MagicMock(name=domain_id)
        domain.id = domain_id
        domain.status = status
        domains.append(domain)
    return storage, domains


def _run(domain_statuses, exclude_domains=None):
    storage, domains = _storage(domain_statuses)
    # ``Storage`` resolves its columns through ``__getattr__``, so they are set
    # on the instance rather than patched on the class.
    object.__setattr__(storage, "id", "storage-1")
    object.__setattr__(storage, "status", "ready")
    with patch.object(
        Storage, "domains", new_callable=PropertyMock, return_value=domains
    ), patch.object(
        Storage, "children", new_callable=PropertyMock, return_value=[]
    ), patch.object(
        Storage, "__setattr__", object.__setattr__
    ):
        # ``__setattr__`` persists to rethinkdb; the assertions are on the
        # domains, so keeping the write in memory is enough.
        storage.set_maintenance("delete", exclude_domains=exclude_domains)
    return domains


def test_the_desktop_being_deleted_does_not_block_its_own_disk():
    domains = _run({"desktop-1": "Started"}, exclude_domains=["desktop-1"])
    # And it is still parked, so the row says a task owns it while it happens.
    assert domains[0].status == "Maintenance"
    assert domains[0].current_action == "delete"


def test_another_running_desktop_on_the_same_disk_still_blocks_it():
    with pytest.raises(Exception) as raised:
        _run(
            {"desktop-1": "Started", "desktop-2": "Started"},
            exclude_domains=["desktop-1"],
        )
    assert raised.value.args[2] == "desktops_not_stopped"


def test_without_the_exclusion_a_running_desktop_still_blocks_it():
    """The default is unchanged for every other caller."""
    with pytest.raises(Exception) as raised:
        _run({"desktop-1": "Started"})
    assert raised.value.args[2] == "desktops_not_stopped"
