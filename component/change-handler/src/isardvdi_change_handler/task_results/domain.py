#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
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

"""Domain-side task_results handlers ported from core_worker."""

from isardvdi_common.models.domain import Domain
from isardvdi_common.models.storage import Storage

# Statuses a domain can be in at the start of the task-based creation
# chain. Used to detect whether ``domain_creating_disk`` /
# ``domain_change_storage`` should advance the row or leave it alone.
# Kept aligned with core_worker.task's matching frozensets.
_DOMAIN_CREATE_TO_CREATING_DOMAIN = frozenset(
    {
        "Creating",
        "CreatingAndStarting",
        "CreatingDisk",
        "CreatingDiskFromScratch",
    }
)

_DOMAIN_CREATING_TO_CREATING_DISK = frozenset(
    {
        "Creating",
        "CreatingDiskFromScratch",
    }
)


def handle_domain_creating_disk(task, domain_id):
    """Port of core_worker.task.domain_creating_disk."""
    if not Domain.exists(domain_id):
        return
    domain = Domain(domain_id)
    if domain.status in _DOMAIN_CREATING_TO_CREATING_DISK:
        domain.status = "CreatingDisk"


def handle_domain_change_storage(task, domain_id, storage_id):
    """Port of core_worker.task.domain_change_storage.

    Wires a storage into a domain's first disk and, when the domain is
    in a pre-libvirt creation status, advances it to ``CreatingDomain``
    so engine's libvirt-define handler takes over.

    When the storage isn't ready and the domain is still in a create
    state the chain failed upstream (create/qemu-img-info produced a disk
    that ``storage_update`` marked deleted/orphan/broken_chain). This is a
    **terminal** condition, not a transient one: the handler runs in the
    same in-process pass right after ``storage_update``, so a not-ready
    storage will never recover on a redelivery. Fail both rows in place —
    exactly what the trailing ``update_status`` FAILED branch would do —
    and return, instead of raising: a raise leaves the stream entry unACKed
    → redelivered ``MAX_DELIVERIES`` times → dead-lettered for a normal
    condition (#2307). Returning lets the consumer ACK the entry and
    finalise the chain cleanly.
    """
    if not Domain.exists(domain_id):
        return
    if not Storage.exists(storage_id):
        return
    domain = Domain(domain_id)
    storage = Storage(storage_id)

    if domain.status in _DOMAIN_CREATE_TO_CREATING_DOMAIN and storage.status != "ready":
        domain.status = "Failed"
        storage.status = "Failed"
        return

    c_dict = domain.create_dict
    disk = c_dict["hardware"]["disks"][0]
    disk["storage_id"] = storage_id
    disk["file"] = storage.path
    # ``disk["parent"]`` (path-shaped lineage marker) is intentionally
    # NOT written. Earlier this handler resolved ``storage.parent``
    # (UUID) into the parent storage's path and wrote it here for
    # parity with main's ``engine.services.lib.storage.insert_storage``.
    # PR3 audit confirmed zero readers on this branch — engine builds
    # libvirt XML from ``disk["file"]`` only (``domain_xml.py:1763``),
    # ``storage.parent`` is read separately for the resolved_disk
    # ``parent`` field but goes unused in the XML loop, the cascade
    # walks ``domain.parents`` UUIDs, and qemu reads the on-disk
    # backing-file from the qcow2 header. Leaving the field unset
    # avoids a stale lineage marker on every chain step.
    domain.create_dict = c_dict

    if domain.status in _DOMAIN_CREATE_TO_CREATING_DOMAIN:
        domain.status = "CreatingDomain"
