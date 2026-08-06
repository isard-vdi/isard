# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for BastionService — thin façade over Targets, Bastion, and
Alloweds helpers. Tests pin the dispatch + the validation paths
(domain count limit, empty domain rejection) and the authorized_keys
box, which stores other people's keys verbatim: no profile key is ever
written there, the bastion resolves those live at connection time.
"""

from unittest.mock import patch

import pytest
from api.services.bastion import BastionService
from isardvdi_common.helpers.error_factory import Error


class TestGetDesktopBastion:
    @patch(
        "api.services.bastion.Targets.get_domain_target",
        return_value={"id": "t1", "domains": []},
    )
    def test_returns_existing_target(self, mock_get):
        result = BastionService.get_desktop_bastion("desk-1")
        mock_get.assert_called_once_with("desk-1")
        assert result == {"id": "t1", "domains": []}

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
    def test_clears_domains_when_user_lacks_permission(self, mock_update):
        BastionService.update_desktop_bastion(
            "desk-1",
            {"domains": ["foo.example"], "ssh": {}},
            can_use_individual_domains=False,
        )
        forwarded = mock_update.call_args[0][1]
        assert forwarded["domains"] == []

    @patch("api.services.bastion.Targets.update_domain_target")
    def test_keeps_domains_when_user_has_permission(self, mock_update):
        BastionService.update_desktop_bastion(
            "desk-1", {"domains": ["foo.example"]}, can_use_individual_domains=True
        )
        assert mock_update.call_args[0][1]["domains"] == ["foo.example"]


class TestUpdateBastionAuthorizedKeys:
    @patch("api.services.bastion.Targets.update_domain_target")
    @patch(
        "api.services.bastion.Targets.get_domain_target",
        return_value={
            "id": "t1",
            "user_id": "owner",
            "ssh": {"authorized_keys": ["old"]},
        },
    )
    def test_replaces_other_keys(self, _mock_get, mock_update):
        BastionService.update_bastion_authorized_keys("desk-1", ["new-key"])
        forwarded = mock_update.call_args[0][1]["ssh"]["authorized_keys"]
        assert forwarded == ["new-key"]

    @patch("api.services.bastion.Targets.update_domain_target")
    @patch(
        "api.services.bastion.Targets.get_domain_target",
        return_value={
            "id": "t1",
            "user_id": "owner",
            "ssh": {"enabled": True, "port": 2222, "authorized_keys": ["old"]},
        },
    )
    def test_preserves_enabled_and_port(self, _mock_get, mock_update):
        # update_domain_target replaces target["ssh"] wholesale, so the write
        # must carry the rest of the subdocument or SSH silently turns off.
        BastionService.update_bastion_authorized_keys("desk-1", ["new-key"])
        forwarded = mock_update.call_args[0][1]["ssh"]
        assert forwarded["enabled"] is True
        assert forwarded["port"] == 2222

    @patch("api.services.bastion.Targets.update_domain_target")
    @patch(
        "api.services.bastion.Targets.get_domain_target",
        return_value={
            "id": "t1",
            "user_id": "owner",
            "ssh": {"authorized_keys": ["  friend  ", "", "friend", "other"]},
        },
    )
    def test_trims_and_dedups(self, _mock_get, mock_update):
        BastionService.update_bastion_authorized_keys(
            "desk-1", ["  friend  ", "", "friend", "other"]
        )
        forwarded = mock_update.call_args[0][1]["ssh"]["authorized_keys"]
        assert forwarded == ["friend", "other"]

    @patch("api.services.bastion.Targets.update_domain_target")
    @patch(
        "api.services.bastion.Targets.get_domain_target",
        return_value={
            "id": "t1",
            "user_id": "owner",
            "ssh": {"authorized_keys": ["friend"]},
        },
    )
    def test_empty_list_clears_the_box(self, _mock_get, mock_update):
        BastionService.update_bastion_authorized_keys("desk-1", [])
        forwarded = mock_update.call_args[0][1]["ssh"]["authorized_keys"]
        assert forwarded == []

    @patch("api.services.bastion.Targets.update_domain_target")
    @patch(
        "api.services.bastion.Targets.get_domain_target",
        return_value={
            "id": "t1",
            "user_id": "owner",
            "ssh": {"enabled": True, "authorized_keys": ["a", "b"]},
        },
    )
    def test_no_write_when_unchanged(self, _mock_get, mock_update):
        BastionService.update_bastion_authorized_keys("desk-1", ["a", "b"])
        mock_update.assert_not_called()


class TestEnsureBastionConfigOnStart:
    @patch("api.services.bastion.BastionService.apply_bastion_config")
    @patch(
        "api.services.bastion.BastionService._get_desktop_deployment_bastion",
        return_value=None,
    )
    def test_noop_outside_a_deployment(self, _dep, mock_apply):
        BastionService.ensure_bastion_config_on_start("desk-1")
        mock_apply.assert_not_called()

    @patch("api.services.bastion.BastionService.apply_bastion_config")
    @patch(
        "api.services.bastion.BastionService._get_desktop_deployment_bastion",
        return_value={"ssh": {"enabled": True, "port": 22}, "http": {"enabled": False}},
    )
    def test_reconciles_the_deployment_config(self, _dep, mock_apply):
        BastionService.ensure_bastion_config_on_start("desk-1")
        mock_apply.assert_called_once()
        assert mock_apply.call_args[0][0] == "desk-1"

    @patch("api.services.bastion.Targets.update_domain_target")
    @patch(
        "api.services.bastion.BastionService._get_desktop_deployment_bastion",
        return_value=None,
    )
    def test_never_writes_key_material(self, _dep, mock_update):
        BastionService.ensure_bastion_config_on_start("desk-1")
        mock_update.assert_not_called()


class TestApplyBastionConfig:
    @patch("api.services.bastion.Targets.update_domain_target")
    @patch("api.services.bastion.Targets.get_domain_target")
    def test_sets_enabled_and_preserves_keys(self, mock_get, mock_update):
        mock_get.return_value = {
            "id": "t1",
            "user_id": "owner",
            "ssh": {"enabled": False, "port": 22, "authorized_keys": ["k1"]},
            "http": {"enabled": False, "http_port": 80, "https_port": 443},
        }
        BastionService.apply_bastion_config(
            "desk-1",
            {"ssh": {"enabled": True, "port": 2222}, "http": {"enabled": False}},
        )
        forwarded = mock_update.call_args[0][1]
        assert forwarded["ssh"]["enabled"] is True
        assert forwarded["ssh"]["port"] == 2222
        # authorized_keys preserved
        assert forwarded["ssh"]["authorized_keys"] == ["k1"]

    @patch("api.services.bastion.Targets.update_domain_target")
    @patch("api.services.bastion.Targets.get_domain_target")
    def test_no_write_when_unchanged(self, mock_get, mock_update):
        mock_get.return_value = {
            "id": "t1",
            "user_id": "owner",
            "ssh": {"enabled": True, "port": 22, "authorized_keys": []},
            "http": {"enabled": False, "http_port": 80, "https_port": 443},
        }
        BastionService.apply_bastion_config(
            "desk-1",
            {"ssh": {"enabled": True, "port": 22}, "http": {"enabled": False}},
        )
        mock_update.assert_not_called()

    @patch("api.services.bastion.Targets.update_domain_target")
    @patch(
        "api.services.bastion.Targets.get_domain_target",
        side_effect=Error("not_found", "Target not found"),
    )
    def test_creates_target_when_missing(self, _mock_get, mock_update):
        BastionService.apply_bastion_config(
            "desk-1",
            {"ssh": {"enabled": True, "port": 22}, "http": {"enabled": True}},
        )
        forwarded = mock_update.call_args[0][1]
        assert forwarded["ssh"]["enabled"] is True
        assert forwarded["http"]["enabled"] is True


class TestGetDesktopBastionActive:
    @patch(
        "api.services.bastion.Targets.get_domain_target",
        side_effect=Error("not_found", "Target not found"),
    )
    def test_missing_target_returns_disabled(self, _mock_get):
        result = BastionService.get_desktop_bastion_active("desk-1")
        assert result["exists"] is False
        assert result["ssh"]["enabled"] is False

    @patch(
        "api.services.bastion.BastionService.get_admin_bastion_config",
        return_value={
            "bastion_domain": "bastion.example",
            "bastion_ssh_port": "443",
            "bastion_enabled": True,
        },
    )
    @patch("api.services.bastion.Targets.get_domain_target")
    def test_existing_target_reflects_enabled(self, mock_get, _cfg):
        mock_get.return_value = {
            "id": "t1",
            "user_id": "owner",
            "domains": [],
            "ssh": {"enabled": True, "port": 22, "authorized_keys": ["k"]},
            "http": {"enabled": False, "http_port": 80, "https_port": 443},
        }
        result = BastionService.get_desktop_bastion_active("desk-1")
        assert result["exists"] is True
        # authorized_keys must NOT be exposed by the read-only status
        assert result["ssh"] == {"enabled": True, "port": 22}
        assert result["bastion_domain"] == "bastion.example"


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
