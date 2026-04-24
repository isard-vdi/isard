# SPDX-License-Identifier: AGPL-3.0-or-later

"""Resolve the parent disk path of a domain across shape variants.

Kept in its own module (no cross-domain imports) so that both
``templates.py`` and ``desktops.py`` can depend on it without triggering
the long-standing circular chain between the two.
"""

from isardvdi_common.helpers.error_factory import Error


def resolve_parent_disk(domain):
    """Return the on-disk path of the first qcow2 disk in a domain.

    Handles three shapes produced by different code paths on the unified
    branch: (a) downloaded/engine-managed domains whose
    ``create_dict.hardware.disks[0]`` only carries ``storage_id`` and
    resolves the path via the ``Storage`` model; (b) legacy v3 domains
    with an explicit ``file`` key under the same path; (c) very old
    domains whose disks still live in the top-level ``hardware.disks``
    that ``42a235720`` strips on new downloads but may still exist in
    long-lived databases.
    """
    # Lazy import to keep this module import-cycle-free. Storage pulls
    # the full RethinkCustomBase stack which indirectly re-enters the
    # domain modules.
    from isardvdi_common.models.storage import Storage

    cd_disks = domain.get("create_dict", {}).get("hardware", {}).get("disks", []) or []
    if cd_disks:
        disk0 = cd_disks[0]
        storage_id = disk0.get("storage_id")
        if storage_id:
            return Storage(storage_id).path
        if disk0.get("file"):
            return disk0["file"]

    hw_disks = domain.get("hardware", {}).get("disks", []) or []
    if hw_disks and hw_disks[0].get("file"):
        return hw_disks[0]["file"]

    raise Error(
        "internal_server",
        f"Domain {domain.get('id')} has no resolvable parent disk.",
        description_code="domain_no_parent_disk",
    )
