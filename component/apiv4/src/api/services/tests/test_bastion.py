# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for BastionService — thin façade over Targets, Bastion, and
Alloweds helpers. Tests pin the dispatch + the validation paths
(domain count limit, empty authorized_keys / domain rejections).
"""

from unittest.mock import patch

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
        "api.services.bastion.BastionService._get_user_bastion_key",
        return_value=None,
    )
    @patch(
        "api.services.bastion.Targets.get_domain_target",
        return_value={
            "id": "t1",
            "user_id": "owner",
            "ssh": {"authorized_keys": ["old"]},
        },
    )
    def test_replaces_other_keys(self, _mock_get, _mock_key, mock_update):
        # No owner profile key -> the submitted "other" keys are stored as-is.
        BastionService.update_bastion_authorized_keys("desk-1", ["new-key"])
        forwarded = mock_update.call_args[0][1]["ssh"]["authorized_keys"]
        assert forwarded == ["new-key"]

    @patch("api.services.bastion.Targets.update_domain_target")
    @patch("api.services.bastion.BastionService._get_user_bastion_key")
    @patch("api.services.bastion.Targets.get_domain_target")
    def test_keeps_owner_first_and_strips_editor(self, mock_get, mock_key, mock_update):
        mock_get.return_value = {
            "id": "t1",
            "user_id": "owner",
            "ssh": {"authorized_keys": []},
        }
        mock_key.side_effect = lambda uid: {
            "owner": "owner-key",
            "editor": "editor-key",
        }.get(uid)
        # The editor (a non-owner) submits their own key among the "others":
        # it is stripped, and the owner key is re-prepended at index 0.
        BastionService.update_bastion_authorized_keys(
            "desk-1", ["editor-key", "friend"], "editor"
        )
        forwarded = mock_update.call_args[0][1]["ssh"]["authorized_keys"]
        assert forwarded == ["owner-key", "friend"]

    @patch("api.services.bastion.Targets.update_domain_target")
    @patch(
        "api.services.bastion.BastionService._get_user_bastion_key",
        return_value="owner-key",
    )
    @patch(
        "api.services.bastion.Targets.get_domain_target",
        return_value={
            "id": "t1",
            "user_id": "owner",
            "ssh": {"authorized_keys": ["owner-key"]},
        },
    )
    def test_allows_empty_keys_and_keeps_owner(self, _mock_get, _mock_key, mock_update):
        # An empty "others" list is now allowed; the owner key is preserved, so
        # nothing actually changes and no write happens.
        BastionService.update_bastion_authorized_keys("desk-1", [])
        mock_update.assert_not_called()


class TestNormalizeAuthorizedKeys:
    @patch("api.services.bastion.Targets.update_domain_target")
    @patch("api.services.bastion.BastionService._get_user_bastion_key")
    @patch("api.services.bastion.Targets.get_domain_target")
    def test_owner_first_and_dedup(self, mock_get, mock_key, mock_update):
        mock_get.return_value = {
            "id": "t1",
            "user_id": "owner",
            "ssh": {
                "enabled": True,
                "port": 22,
                "authorized_keys": ["owner-key", "friend", "owner-key"],
            },
        }
        mock_key.side_effect = lambda uid: {"owner": "owner-key"}.get(uid)
        result = BastionService.normalize_authorized_keys("desk-1")
        assert result == ["owner-key", "friend"]
        forwarded = mock_update.call_args[0][1]["ssh"]["authorized_keys"]
        assert forwarded == ["owner-key", "friend"]

    @patch("api.services.bastion.Targets.update_domain_target")
    @patch("api.services.bastion.BastionService._get_user_bastion_key")
    @patch("api.services.bastion.Targets.get_domain_target")
    def test_ensures_actor_key_after_owner(self, mock_get, mock_key, mock_update):
        mock_get.return_value = {
            "id": "t1",
            "user_id": "owner",
            "ssh": {"enabled": True, "authorized_keys": ["friend"]},
        }
        mock_key.side_effect = lambda uid: {
            "owner": "owner-key",
            "admin": "admin-key",
        }.get(uid)
        result = BastionService.normalize_authorized_keys(
            "desk-1", ensure_user_ids=["admin"]
        )
        assert result == ["owner-key", "admin-key", "friend"]

    @patch("api.services.bastion.Targets.update_domain_target")
    @patch(
        "api.services.bastion.BastionService._get_user_bastion_key",
        return_value=None,
    )
    @patch("api.services.bastion.Targets.get_domain_target")
    def test_no_write_when_unchanged(self, mock_get, _mock_key, mock_update):
        mock_get.return_value = {
            "id": "t1",
            "user_id": "owner",
            "ssh": {"enabled": True, "authorized_keys": ["a", "b"]},
        }
        result = BastionService.normalize_authorized_keys("desk-1")
        assert result == ["a", "b"]
        mock_update.assert_not_called()


class TestEnsureKeysOnStart:
    @patch("api.services.bastion.Targets.update_domain_target")
    @patch("api.services.bastion.Targets.get_domain_target")
    def test_noop_when_ssh_disabled(self, mock_get, mock_update):
        mock_get.return_value = {
            "id": "t1",
            "user_id": "owner",
            "ssh": {"enabled": False, "authorized_keys": []},
        }
        BastionService.ensure_keys_on_start("desk-1", "owner")
        mock_update.assert_not_called()

    @patch("api.services.bastion.Targets.update_domain_target")
    @patch(
        "api.services.bastion.Targets.get_domain_target",
        side_effect=Error("not_found", "Target not found"),
    )
    def test_noop_when_no_target(self, _mock_get, mock_update):
        BastionService.ensure_keys_on_start("desk-1", "owner")
        mock_update.assert_not_called()

    @patch("api.services.bastion.Targets.update_domain_target")
    @patch("api.services.bastion.BastionService._get_user_bastion_key")
    @patch("api.services.bastion.Targets.get_domain_target")
    def test_injects_actor_key_owner_first(self, mock_get, mock_key, mock_update):
        mock_get.return_value = {
            "id": "t1",
            "user_id": "owner",
            "ssh": {"enabled": True, "port": 22, "authorized_keys": ["friend"]},
        }
        mock_key.side_effect = lambda uid: {
            "owner": "owner-key",
            "admin": "admin-key",
        }.get(uid)
        BastionService.ensure_keys_on_start("desk-1", "admin")
        forwarded = mock_update.call_args[0][1]["ssh"]["authorized_keys"]
        assert forwarded == ["owner-key", "admin-key", "friend"]


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
            "domain": None,
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
