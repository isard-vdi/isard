#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin the ``Disk.bus`` legacy-bool normalisation.

Historical desktops persisted ``bus: False`` (raw bool) in their
``create_dict.hardware.disks[]``. The deployment-edit revalidation
through ``DeploymentUpdateModel`` would 500 because the strict
``Optional[str]`` rejects bool. The ``Disk`` schema now coerces the
legacy ``False`` into ``None`` via a pre-validator.
"""

import pytest
from isardvdi_common.schemas.shared.hardware import Disk


class TestDiskBusNormalisation:
    def test_bus_false_becomes_none(self):
        disk = Disk(storage_id="s1", bus=False)
        assert disk.bus is None

    def test_bus_string_passes_through(self):
        disk = Disk(storage_id="s1", bus="virtio")
        assert disk.bus == "virtio"

    def test_bus_none_stays_none(self):
        disk = Disk(storage_id="s1", bus=None)
        assert disk.bus is None

    def test_bus_default_is_none(self):
        # Field default; no value supplied. Must not be False (the
        # legacy bug) and must validate as Optional[str].
        disk = Disk(storage_id="s1")
        assert disk.bus is None

    def test_bus_empty_string_passes_through(self):
        # Empty string is a legitimate "no bus declared" — keep it
        # as-is so callers that distinguish from None don't break.
        disk = Disk(storage_id="s1", bus="")
        assert disk.bus == ""

    def test_legacy_deployment_disks_revalidate(self):
        # Mirrors the journal repro: a list of disks where the first
        # entry carries ``bus: False`` from a historical row.
        legacy_payload = [
            {"storage_id": "s1", "bus": False, "extension": "qcow2"},
            {"storage_id": "s2", "bus": "virtio"},
        ]
        disks = [Disk(**row) for row in legacy_payload]
        assert disks[0].bus is None
        assert disks[1].bus == "virtio"

    def test_bus_true_is_left_for_strict_rejection(self):
        # Only ``False`` is normalised; other bools should still
        # surface a validation error so the schema doesn't quietly
        # accept arbitrary truthy values.
        with pytest.raises(Exception):
            Disk(storage_id="s1", bus=True)
