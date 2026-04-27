# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_hypervisors.py``."""

import pytest
from api.schemas.admin_hypervisors import (
    AdminHypervisorCreateData,
    AdminHypervisorDisksFoundData,
    AdminHypervisorEnableData,
    AdminHypervisorMediaDeleteData,
    AdminHypervisorMediaFoundData,
    AdminHypervisorVirtPoolUpdateData,
    AdminHypervisorWgAddrData,
)
from pydantic import ValidationError


class TestAdminHypervisorCreateData:
    _required = {"hyper_id": "h-1", "hostname": "hyper.example.com"}

    def test_accepts_required(self):
        h = AdminHypervisorCreateData(**self._required)
        assert h.hyper_id == "h-1"
        # Defaults — pin them so an admin form that omits them still
        # lands on the canonical values.
        assert h.user == "root"
        assert h.port == "2022"
        assert h.cap_disk is True
        assert h.cap_hyper is True
        assert h.enabled is False
        assert h.browser_port == "443"
        assert h.spice_port == "80"
        assert h.isard_proxy_hyper_url == "isard-hypervisor"
        assert h.description == "Added via api"
        assert h.only_forced is False
        assert h.nvidia_enabled is False
        assert h.force_get_hyp_info is False
        assert h.min_free_mem_gb == 0
        assert h.buffering_hyper is False
        assert h.gpu_only is False

    @pytest.mark.parametrize("missing", ["hyper_id", "hostname"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            AdminHypervisorCreateData(**payload)


class TestAdminHypervisorEnableData:
    def test_default_enabled_true(self):
        """The enable endpoint defaults `enabled` to True — sending an
        empty body means "enable". Pin so a default flip is noticed."""
        h = AdminHypervisorEnableData()
        assert h.enabled is True
        assert h.numa_topology is None

    def test_accepts_disable(self):
        h = AdminHypervisorEnableData(enabled=False)
        assert h.enabled is False

    def test_numa_topology_arbitrary(self):
        h = AdminHypervisorEnableData(numa_topology={"cores": 32, "sockets": 2})
        assert h.numa_topology["cores"] == 32


class TestAdminHypervisorWgAddrData:
    @pytest.mark.parametrize("missing", ["mac", "ip"])
    def test_both_required(self, missing):
        payload = {"mac": "aa:bb:cc:dd:ee:ff", "ip": "10.0.0.1"}
        del payload[missing]
        with pytest.raises(ValidationError):
            AdminHypervisorWgAddrData(**payload)


class TestAdminHypervisorMediaFoundData:
    def test_medias_required(self):
        with pytest.raises(ValidationError):
            AdminHypervisorMediaFoundData()

    def test_accepts_empty_list(self):
        h = AdminHypervisorMediaFoundData(medias=[])
        assert h.medias == []


class TestAdminHypervisorDisksFoundData:
    def test_disks_required(self):
        with pytest.raises(ValidationError):
            AdminHypervisorDisksFoundData()

    def test_accepts_arbitrary_list(self):
        h = AdminHypervisorDisksFoundData(disks=[{"path": "/d1.qcow2"}])
        assert h.disks == [{"path": "/d1.qcow2"}]


class TestAdminHypervisorMediaDeleteData:
    def test_paths_required(self):
        with pytest.raises(ValidationError):
            AdminHypervisorMediaDeleteData()


class TestAdminHypervisorVirtPoolUpdateData:
    _required = {"id": "vp-1", "enable_virt_pool": True}

    def test_accepts_required(self):
        h = AdminHypervisorVirtPoolUpdateData(**self._required)
        assert h.id == "vp-1"
        assert h.enable_virt_pool is True

    @pytest.mark.parametrize("missing", ["id", "enable_virt_pool"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            AdminHypervisorVirtPoolUpdateData(**payload)
