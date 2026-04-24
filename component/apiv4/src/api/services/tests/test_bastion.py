# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for BastionService — thin façade over Targets, Bastion, and
Alloweds helpers. Tests pin the dispatch + the validation paths
(domain count limit, empty authorized_keys / domain rejections).
"""

from unittest.mock import patch

import pytest
from api.services.bastion import BastionService
from isardvdi_common.helpers.error_factory import Error


class TestGetDesktopBastion:
    @patch(
        "api.services.bastion.Targets.get_domain_target",
        return_value={"id": "t1", "domain": None},
    )
    def test_returns_existing_target(self, mock_get):
        result = BastionService.get_desktop_bastion("desk-1")
        mock_get.assert_called_once_with("desk-1")
        assert result == {"id": "t1", "domain": None}

    @patch(
        "api.services.bastion.Targets.update_domain_target",
        return_value={"id": "t-new"},
    )
    @patch(
        "api.services.bastion.Targets.get_domain_target",
        side_effect=Exception("not found"),
    )
    def test_creates_empty_target_when_missing(self, _mock_get, mock_update):
        result = BastionService.get_desktop_bastion("desk-1")
        mock_update.assert_called_once_with("desk-1", {})
        assert result == {"id": "t-new"}


class TestUpdateDesktopBastion:
    @patch("api.services.bastion.Targets.update_domain_target")
    def test_clears_domain_when_user_lacks_permission(self, mock_update):
        BastionService.update_desktop_bastion(
            "desk-1",
            {"domain": "foo.example", "ssh": {}},
            can_use_individual_domains=False,
        )
        forwarded = mock_update.call_args[0][1]
        assert forwarded["domain"] is None

    @patch("api.services.bastion.Targets.update_domain_target")
    def test_keeps_domain_when_user_has_permission(self, mock_update):
        BastionService.update_desktop_bastion(
            "desk-1", {"domain": "foo.example"}, can_use_individual_domains=True
        )
        assert mock_update.call_args[0][1]["domain"] == "foo.example"


class TestUpdateBastionAuthorizedKeys:
    @patch("api.services.bastion.Targets.update_domain_target")
    @patch(
        "api.services.bastion.Targets.get_domain_target",
        return_value={"id": "t1", "ssh": {"authorized_keys": ["old"]}},
    )
    def test_replaces_authorized_keys(self, _mock_get, mock_update):
        BastionService.update_bastion_authorized_keys("desk-1", ["new-key"])
        forwarded = mock_update.call_args[0][1]
        assert forwarded == {"ssh": {"authorized_keys": ["new-key"]}}

    def test_rejects_empty_keys(self):
        with pytest.raises(Error):
            BastionService.update_bastion_authorized_keys("desk-1", [])


class TestUpdateBastionDomains:
    @patch("api.services.bastion.Targets.update_domain_target")
    @patch("api.services.bastion.Bastion.check_duplicate_bastion_domains")
    @patch("api.services.bastion.Targets.get_domain_target", return_value={"id": "t1"})
    def test_strips_whitespace_and_filters_empties(
        self, _mock_get, _mock_dup, mock_update
    ):
        BastionService.update_bastion_domains(
            "desk-1", ["  a.com ", "", "  ", "b.com"], "default"
        )
        forwarded = mock_update.call_args[0][1]["domains"]
        assert forwarded == ["a.com", "b.com"]

    @patch("api.services.bastion.Targets.get_domain_target", return_value={"id": "t1"})
    def test_rejects_more_than_ten_domains(self, _mock_get):
        with pytest.raises(Error):
            BastionService.update_bastion_domains(
                "desk-1", [f"d{i}.com" for i in range(11)], "default"
            )


class TestVerifyBastionDomain:
    def test_rejects_empty_domain(self):
        with pytest.raises(Error):
            BastionService.verify_bastion_domain("desk-1", "   ", "default")

    @patch(
        "api.services.bastion.Bastion.bastion_domain_verification_required",
        return_value=False,
    )
    @patch("api.services.bastion.Bastion.check_duplicate_bastion_domains")
    @patch("api.services.bastion.Targets.get_domain_target", return_value={"id": "t1"})
    def test_skips_dns_check_when_not_required(self, _g, _dup, _req):
        # When verification isn't required, verify_bastion_domain just runs the
        # duplicate check and returns verified=True without touching DNS.
        result = BastionService.verify_bastion_domain("desk-1", "foo.com", "default")
        assert result == {"verified": True}
