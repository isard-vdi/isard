# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_resources.py``."""

import pytest
from api.schemas.admin_resources import QosDiskCreateRequest, QosDiskUpdateRequest
from pydantic import ValidationError


class TestQosDiskCreateRequest:
    _required = {
        "name": "Standard",
        "iotune": {"read_iops_sec": 1000, "write_iops_sec": 500},
    }

    def test_accepts_required(self):
        r = QosDiskCreateRequest(**self._required)
        assert r.name == "Standard"
        assert r.iotune["read_iops_sec"] == 1000
        # Optional fields default to None.
        assert r.id is None
        assert r.description is None
        assert r.allowed is None

    @pytest.mark.parametrize("missing", ["name", "iotune"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            QosDiskCreateRequest(**payload)

    def test_iotune_arbitrary_dict(self):
        """iotune: dict — pin the wide net so libvirt-specific knobs
        (total_bytes_sec_max, etc.) pass through without schema updates."""
        r = QosDiskCreateRequest(
            name="x",
            iotune={"total_bytes_sec_max": 10485760, "anything": True},
        )
        assert r.iotune["anything"] is True


class TestQosDiskUpdateRequest:
    _required = {"id": "q-1", "name": "Updated"}

    def test_accepts_required(self):
        r = QosDiskUpdateRequest(**self._required)
        assert r.id == "q-1"
        # iotune is now Optional on Update (it's required on Create).
        assert r.iotune is None

    @pytest.mark.parametrize("missing", ["id", "name"])
    def test_id_and_name_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            QosDiskUpdateRequest(**payload)

    def test_iotune_optional_on_update(self):
        """Asymmetry with Create: iotune is required on Create but
        Optional on Update (rename-only changes are valid). Pin so
        a future schema sync that re-aligns them is intentional."""
        r = QosDiskUpdateRequest(id="q-1", name="Renamed")
        assert r.model_dump(exclude_none=True) == {"id": "q-1", "name": "Renamed"}
