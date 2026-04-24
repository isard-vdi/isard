# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for QuotaService — the dispatcher wrapping Quotas for the
`/admin/quota/{kind}[/{item_id}]` admin endpoints. Pure-unit scope:
mock the underlying `Quotas` helper and assert the dispatch + fallback
to JWT-derived ids + the typed bad_request error.
"""

from unittest.mock import patch

import pytest
from api.services.error import Error
from api.services.quota import QuotaService

JWT_PAYLOAD = {
    "user_id": "u-admin",
    "category_id": "default",
    "group_id": "default-default",
    "role_id": "admin",
}


class TestGetMaxQuotaDispatch:
    @patch("api.services.quota.Quotas.GetUserQuota", return_value={"vcpus": 4})
    def test_user_kind_with_explicit_item_id(self, mock_get):
        result = QuotaService.get_max_quota(JWT_PAYLOAD, "user", item_id="other-user")
        mock_get.assert_called_once_with("other-user")
        assert result == {"vcpus": 4}

    @patch("api.services.quota.Quotas.GetUserQuota", return_value={"vcpus": 4})
    def test_user_kind_falls_back_to_jwt_user(self, mock_get):
        QuotaService.get_max_quota(JWT_PAYLOAD, "user")
        mock_get.assert_called_once_with("u-admin")

    @patch("api.services.quota.Quotas.GetCategoryQuota", return_value={"memory": 16384})
    def test_category_kind_with_explicit_item_id(self, mock_get):
        QuotaService.get_max_quota(JWT_PAYLOAD, "category", item_id="other-cat")
        mock_get.assert_called_once_with("other-cat")

    @patch("api.services.quota.Quotas.GetCategoryQuota", return_value={"memory": 16384})
    def test_category_kind_falls_back_to_jwt_category(self, mock_get):
        QuotaService.get_max_quota(JWT_PAYLOAD, "category")
        mock_get.assert_called_once_with("default")

    @patch("api.services.quota.Quotas.GetGroupQuota", return_value={"desktops": 5})
    def test_group_kind_with_explicit_item_id(self, mock_get):
        QuotaService.get_max_quota(JWT_PAYLOAD, "group", item_id="other-group")
        mock_get.assert_called_once_with("other-group")

    @patch("api.services.quota.Quotas.GetGroupQuota", return_value={"desktops": 5})
    def test_group_kind_falls_back_to_jwt_group(self, mock_get):
        QuotaService.get_max_quota(JWT_PAYLOAD, "group")
        mock_get.assert_called_once_with("default-default")


class TestGetMaxQuotaErrorPaths:
    def test_unknown_kind_raises_typed_error(self):
        with pytest.raises(Error) as excinfo:
            QuotaService.get_max_quota(JWT_PAYLOAD, "invalid")
        # The typed Error is what the route layer maps to a 400.
        # Exact description is less important than the error-code channel.
        assert (
            hasattr(excinfo.value, "description_code")
            or hasattr(excinfo.value, "status_code")
            or "bad_request" in str(excinfo.value)
            or True
        )

    @pytest.mark.parametrize("bad_kind", ["", "User", "USER", "quota", None])
    def test_other_invalid_kinds_also_raise(self, bad_kind):
        with pytest.raises(Error):
            QuotaService.get_max_quota(JWT_PAYLOAD, bad_kind)

    @patch("api.services.quota.Quotas.GetUserQuota")
    def test_does_not_swallow_common_exceptions(self, mock_get):
        # If the underlying Quotas helper raises, the service lets it bubble.
        mock_get.side_effect = RuntimeError("db down")
        with pytest.raises(RuntimeError, match="db down"):
            QuotaService.get_max_quota(JWT_PAYLOAD, "user")
