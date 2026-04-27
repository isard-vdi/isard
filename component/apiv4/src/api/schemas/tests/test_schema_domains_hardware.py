# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/domains/hardware.py``."""

import pytest
from api.schemas.domains.hardware import (
    Disk,
    DomainGuestProperties,
    DomainHardware,
    DomainImage,
    DomainImageFile,
    MediaHardware,
    Reservables,
)
from pydantic import ValidationError


class TestDomainImageFile:
    @pytest.mark.parametrize("missing", ["data", "filename"])
    def test_required(self, missing):
        payload = {"data": "iVBOR...", "filename": "card.png"}
        del payload[missing]
        with pytest.raises(ValidationError):
            DomainImageFile(**payload)


class TestDomainImage:
    _required = {"id": "img-1", "type": "stock"}

    def test_accepts_required(self):
        i = DomainImage(**self._required)
        assert i.id == "img-1"
        assert i.url is None
        assert i.file is None

    @pytest.mark.parametrize("missing", ["id", "type"])
    def test_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            DomainImage(**payload)

    def test_file_excluded_from_serialization(self):
        """``file`` carries `exclude=True` — it's a write-only upload
        payload and must NOT appear in any JSON serialization. Pin so
        a refactor that drops `exclude=True` doesn't accidentally leak
        the base64-encoded user card across the wire."""
        i = DomainImage(
            **self._required,
            file={"data": "iVBOR...", "filename": "card.png"},
        )
        assert i.file is not None  # accepted on input
        dump = i.model_dump()
        assert "file" not in dump  # but not serialized


class TestReservables:
    def test_default_none(self):
        r = Reservables()
        assert r.vgpus is None

    def test_accepts_list(self):
        r = Reservables(vgpus=["gpu-1", "gpu-2"])
        assert r.vgpus == ["gpu-1", "gpu-2"]

    def test_accepts_explicit_none(self):
        """vgpus is Optional[list[str]] | None — explicit None is "no
        vGPUs". Pin so the union branch doesn't change semantically."""
        r = Reservables(vgpus=None)
        assert r.vgpus is None


class TestDomainHardware:
    """Validates the hardware constraints — these are critical for
    capacity calculations."""

    def test_defaults(self):
        h = DomainHardware()
        assert h.memory == 1
        assert h.vcpus == 1
        assert h.boot_order == ["disk"]
        assert h.disk_bus == "Default"
        assert h.videos == ["default"]

    def test_memory_minimum_0_025(self):
        """memory >= 0.025 GB. Pin so a value just below the bound
        is rejected (catches rounding-down regressions)."""
        with pytest.raises(ValidationError):
            DomainHardware(memory=0.024)
        DomainHardware(memory=0.025)  # boundary accepted

    def test_vcpus_minimum_1(self):
        with pytest.raises(ValidationError):
            DomainHardware(vcpus=0)
        DomainHardware(vcpus=1)

    def test_boot_order_literal_constraint(self):
        """boot_order entries must be in {iso, floppy, disk, pxe}."""
        DomainHardware(boot_order=["iso", "disk"])
        with pytest.raises(ValidationError):
            DomainHardware(boot_order=["network"])


class TestDomainGuestProperties:
    def test_defaults(self):
        g = DomainGuestProperties()
        assert g.credentials is None
        assert g.fullscreen is False
        assert g.viewers is None

    def test_credentials_defaults(self):
        """When credentials sub-model is constructed, both fields
        default to the canonical isard/pirineus pair."""
        creds = DomainGuestProperties._GuestPropertiesCredentials()
        assert creds.username == "isard"
        assert creds.password == "pirineus"

    def test_full_nested(self):
        g = DomainGuestProperties(
            credentials={"username": "u", "password": "p"},
            fullscreen=True,
            viewers={"browser_vnc": {"options": {"scale": "2.0"}}},
        )
        assert g.credentials.username == "u"
        assert g.viewers.browser_vnc.options == {"scale": "2.0"}


class TestMediaHardware:
    """Stricter than DomainHardware — every field is required for the
    'create desktop from media' flow."""

    _required = {
        "boot_order": ["disk"],
        "disk_bus": "virtio",
        "disk_size": 10,
        "interfaces": ["default"],
        "memory": 2,
        "vcpus": 2,
        "videos": ["default"],
    }

    @pytest.mark.parametrize("missing", list(_required))
    def test_every_field_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            MediaHardware(**payload)

    def test_disk_size_minimum_1(self):
        """disk_size >= 1 GB."""
        with pytest.raises(ValidationError):
            MediaHardware(**{**self._required, "disk_size": 0})

    def test_memory_minimum_same_as_DomainHardware(self):
        with pytest.raises(ValidationError):
            MediaHardware(**{**self._required, "memory": 0.024})

    def test_vcpus_minimum_1(self):
        with pytest.raises(ValidationError):
            MediaHardware(**{**self._required, "vcpus": 0})


class TestDisk:
    def test_storage_id_required(self):
        with pytest.raises(ValidationError):
            Disk()

    def test_accepts(self):
        assert Disk(storage_id="s-1").storage_id == "s-1"
