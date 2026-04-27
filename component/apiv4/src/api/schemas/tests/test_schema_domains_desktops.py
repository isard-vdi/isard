# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/domains/desktops.py``.

Focuses on the request bodies and key response shapes. Pure data
shapes (UserDesktop, DesktopDetailsResponse) get the lightest touch
since they mirror DB rows that change frequently.
"""

import pytest
from api.schemas.domains.desktops import (
    BastionAuthorizedKeysUpdateRequest,
    BastionDomainsUpdateRequest,
    BastionDomainUpdateRequest,
    BastionDomainVerifyRequest,
    BastionDomainVerifyResponse,
    BulkCreatePersistentDesktopsRequest,
    BulkEditDesktopsRequest,
    CreateDesktopFromMedia,
    CreateDesktopRequest,
    DesktopFilterParams,
    DesktopGetViewerResponse,
    DesktopImageType,
    DesktopNamedResource,
    DesktopNetwork,
    DesktopNetworksResponse,
    DesktopsStopRequest,
    DesktopStorage,
    DesktopTemplate,
    NewNonpersistentDesktopRequest,
    UserDesktopProgress,
    UserDesktopScheduled,
)
from pydantic import ValidationError


class TestCreateDesktopRequest:
    _required = {"template_id": "t-1", "name": "MyDesktop"}

    def test_accepts_required(self):
        r = CreateDesktopRequest(**self._required)
        assert r.persistent is True  # default
        assert r.description is None
        assert r.guest_properties is None
        assert r.hardware is None
        assert r.bastion_target is None

    @pytest.mark.parametrize("missing", ["template_id", "name"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            CreateDesktopRequest(**payload)

    def test_name_min_length_4(self):
        with pytest.raises(ValidationError):
            CreateDesktopRequest(template_id="t-1", name="abc")

    def test_name_max_length_50(self):
        with pytest.raises(ValidationError):
            CreateDesktopRequest(template_id="t-1", name="x" * 51)

    def test_description_max_length_255(self):
        with pytest.raises(ValidationError):
            CreateDesktopRequest(**self._required, description="x" * 256)


class TestDesktopsStopRequest:
    def test_force_default_false(self):
        """force defaults to False — graceful shutdown is the default
        path. Pin so a future flip to forceful default would 500 the
        guest OS in flight."""
        r = DesktopsStopRequest()
        assert r.force is False

    def test_accepts_explicit_true(self):
        assert DesktopsStopRequest(force=True).force is True


class TestSimpleDataShapes:
    """DesktopNetwork, DesktopNamedResource, DesktopStorage, DesktopTemplate
    are simple data wrappers — one required-set check each."""

    def test_desktop_network(self):
        with pytest.raises(ValidationError):
            DesktopNetwork()
        n = DesktopNetwork(id="n-1", name="default", mac="aa:bb:cc:dd:ee:ff")
        assert n.mac == "aa:bb:cc:dd:ee:ff"

    def test_desktop_named_resource(self):
        with pytest.raises(ValidationError):
            DesktopNamedResource()

    def test_desktop_storage(self):
        with pytest.raises(ValidationError):
            DesktopStorage()
        s = DesktopStorage(id="s-1", size=10.5)
        assert s.size == 10.5

    def test_desktop_template(self):
        with pytest.raises(ValidationError):
            DesktopTemplate()


class TestDesktopNetworksResponse:
    def test_default_empty_list(self):
        r = DesktopNetworksResponse()
        assert r.networks == []


class TestBastionAuthorizedKeysUpdateRequest:
    def test_default_empty_list(self):
        """Default = []. Empty list = "wipe authorized_keys". Pin both."""
        r = BastionAuthorizedKeysUpdateRequest()
        assert r.authorized_keys == []


class TestBastionDomainUpdateRequest:
    def test_domain_required(self):
        """domain_name has no default — must be explicitly supplied
        (even None)."""
        with pytest.raises(ValidationError):
            BastionDomainUpdateRequest()

    def test_accepts_none(self):
        """domain_name accepts None to clear the bastion domain."""
        r = BastionDomainUpdateRequest(domain_name=None)
        assert r.domain_name is None


class TestNewNonpersistentDesktopRequest:
    """v3-parity minimal body — single template_id."""

    def test_template_id_required(self):
        with pytest.raises(ValidationError):
            NewNonpersistentDesktopRequest()


class TestBastionDomainsUpdateRequest:
    def test_default_empty_list(self):
        r = BastionDomainsUpdateRequest()
        assert r.domains == []

    def test_max_10_domains(self):
        BastionDomainsUpdateRequest(domains=[f"d{i}.x" for i in range(10)])
        with pytest.raises(ValidationError):
            BastionDomainsUpdateRequest(domains=[f"d{i}.x" for i in range(11)])


class TestBastionDomainVerifyRequest:
    def test_min_length_1(self):
        with pytest.raises(ValidationError):
            BastionDomainVerifyRequest(domain="")


class TestBastionDomainVerifyResponse:
    def test_verified_required(self):
        with pytest.raises(ValidationError):
            BastionDomainVerifyResponse()


class TestDesktopImageType:
    def test_stock_only(self):
        """Only "stock" supported today. Pin so adding "user" is a
        deliberate change that updates this test."""
        assert DesktopImageType.stock.value == "stock"
        assert len(list(DesktopImageType)) == 1


class TestUserDesktopScheduled:
    def test_accepts_datetime_false_or_none(self):
        """shutdown is Union[datetime, Literal[False], None] — pin all
        three branches."""
        from datetime import datetime, timezone

        u = UserDesktopScheduled()
        assert u.shutdown is None
        u = UserDesktopScheduled(shutdown=False)
        assert u.shutdown is False
        u = UserDesktopScheduled(shutdown="2026-01-01T00:00:00Z")
        assert isinstance(u.shutdown, datetime)


class TestUserDesktopProgress:
    def test_defaults(self):
        p = UserDesktopProgress()
        assert p.percentage == 0
        assert p.throughput_average == "0"
        assert p.time_left == "00:00:00"
        assert p.size == "0k"


class TestDesktopFilterParams:
    def test_all_optional(self):
        p = DesktopFilterParams()
        assert p.tag is None
        assert p.persistent is None


class TestCreateDesktopFromMedia:
    _required = {
        "media_id": "m-1",
        "kind": "iso",
        "os_template": "hw-tmpl-1",
        "name": "DesktopFromIso",
        "guest_properties": {},
        "hardware": {
            "boot_order": ["disk"],
            "disk_bus": "virtio",
            "disk_size": 10,
            "interfaces": ["default"],
            "memory": 2,
            "vcpus": 2,
            "videos": ["default"],
        },
    }

    def test_accepts_required(self):
        r = CreateDesktopFromMedia(**self._required)
        assert r.description == ""  # default

    def test_name_length_bounds(self):
        with pytest.raises(ValidationError):
            CreateDesktopFromMedia(**{**self._required, "name": "abc"})
        with pytest.raises(ValidationError):
            CreateDesktopFromMedia(**{**self._required, "name": "x" * 51})

    def test_description_max_255(self):
        with pytest.raises(ValidationError):
            CreateDesktopFromMedia(**{**self._required, "description": "x" * 256})


class TestBulkEditDesktopsRequest:
    def test_ids_required_min_length_1(self):
        """Pin min_length=1 on `ids` — bulk-edit with no targets is a
        no-op that should fail loud, not silently succeed."""
        with pytest.raises(ValidationError):
            BulkEditDesktopsRequest(ids=[])

    def test_minimal(self):
        r = BulkEditDesktopsRequest(ids=["d-1"])
        assert r.ids == ["d-1"]
        assert r.name is None
        assert r.description is None


class TestBulkCreatePersistentDesktopsRequest:
    def test_only_template_id_required(self):
        with pytest.raises(ValidationError):
            BulkCreatePersistentDesktopsRequest()

    def test_minimal(self):
        r = BulkCreatePersistentDesktopsRequest(
            template_id="t-1",
            name="MyDesktop",
            allowed={"users": ["u-1"]},
        )
        assert r.template_id == "t-1"


class TestDesktopGetViewerResponse:
    """The response carries the actual viewer payload — required."""

    def test_required_set(self):
        with pytest.raises(ValidationError):
            DesktopGetViewerResponse()
