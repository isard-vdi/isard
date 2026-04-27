# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/bastion.py``."""

import pytest
from api.schemas.bastion import (
    AdminBastionConfigResponse,
    AdminBastionConfigUpdateRequest,
    BastionAuthorizedKeysRequest,
    BastionDomainsRequest,
    BastionDomainVerificationConfigResponse,
    BastionDomainVerifyRequest,
    BastionDomainVerifyResponse,
    BastionHttpConfig,
    BastionRequest,
    BastionResponse,
    BastionSshConfig,
)
from pydantic import ValidationError


class TestBastionHttpConfig:
    def test_defaults(self):
        h = BastionHttpConfig()
        assert h.enabled is False
        assert h.http_port == 80
        assert h.https_port == 443


class TestBastionSshConfig:
    def test_defaults(self):
        s = BastionSshConfig()
        assert s.enabled is False
        assert s.port == 22
        assert s.authorized_keys == []

    def test_accepts_keys(self):
        s = BastionSshConfig(authorized_keys=["ssh-rsa AAAA...", None])
        assert len(s.authorized_keys) == 2


class TestBastionResponse:
    _required = {
        "desktop_id": "d-1",
        "http": {},
        "id": "b-1",
        "ssh": {},
        "user_id": "u-1",
    }

    def test_accepts_required(self):
        r = BastionResponse(**self._required)
        assert r.id == "b-1"
        assert r.domain is None
        # domains defaults to []
        assert r.domains == []

    @pytest.mark.parametrize("missing", ["desktop_id", "http", "id", "ssh", "user_id"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            BastionResponse(**payload)


class TestBastionRequest:
    def test_accepts_empty(self):
        r = BastionRequest()
        assert r.http is None
        assert r.ssh is None
        assert r.domain is None

    def test_partial(self):
        r = BastionRequest(http={"enabled": True})
        assert r.http.enabled is True
        assert r.ssh is None


class TestAdminBastionConfigResponse:
    _required = {
        "bastion_enabled": True,
        "bastion_enabled_in_cfg": True,
        "bastion_enabled_in_db": True,
        "bastion_domain": "b.example.com",
        "bastion_ssh_port": "22",
        "domain_verification_required": False,
    }

    def test_accepts_required(self):
        r = AdminBastionConfigResponse(**self._required)
        assert r.bastion_enabled is True

    @pytest.mark.parametrize("missing", list(_required))
    def test_every_field_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            AdminBastionConfigResponse(**payload)

    def test_domain_and_port_can_be_none(self):
        """When bastion is disabled, domain and ssh_port are None
        sentinels (not dropped)."""
        r = AdminBastionConfigResponse(
            **{**self._required, "bastion_domain": None, "bastion_ssh_port": None}
        )
        assert r.bastion_domain is None


class TestAdminBastionConfigUpdateRequest:
    @pytest.mark.parametrize(
        "missing", ["enabled", "bastion_domain", "domain_verification_required"]
    )
    def test_required(self, missing):
        payload = {
            "enabled": True,
            "bastion_domain": "b.x",
            "domain_verification_required": False,
        }
        del payload[missing]
        with pytest.raises(ValidationError):
            AdminBastionConfigUpdateRequest(**payload)


class TestBastionDomainVerificationConfigResponse:
    def test_required(self):
        with pytest.raises(ValidationError):
            BastionDomainVerificationConfigResponse()


class TestBastionAuthorizedKeysRequest:
    def test_keys_required(self):
        with pytest.raises(ValidationError):
            BastionAuthorizedKeysRequest()

    def test_accepts_empty_list(self):
        """Empty list = "wipe all keys" (intentional). Pin so a future
        min-length=1 doesn't sneak in."""
        r = BastionAuthorizedKeysRequest(authorized_keys=[])
        assert r.authorized_keys == []


class TestBastionDomainsRequest:
    def test_max_length_10(self):
        """max_length=10 — Pydantic v2 enforces this. Pin the upper
        bound so a future widening is intentional."""
        r = BastionDomainsRequest(domains=[f"d{i}.x" for i in range(10)])
        assert len(r.domains) == 10
        with pytest.raises(ValidationError):
            BastionDomainsRequest(domains=[f"d{i}.x" for i in range(11)])

    def test_accepts_empty(self):
        """Empty list valid — clears all custom domains."""
        r = BastionDomainsRequest(domains=[])
        assert r.domains == []


class TestBastionDomainVerifyRequest:
    def test_domain_required(self):
        with pytest.raises(ValidationError):
            BastionDomainVerifyRequest()

    def test_min_length_1(self):
        with pytest.raises(ValidationError):
            BastionDomainVerifyRequest(domain="")


class TestBastionDomainVerifyResponse:
    def test_verified_required(self):
        with pytest.raises(ValidationError):
            BastionDomainVerifyResponse()
