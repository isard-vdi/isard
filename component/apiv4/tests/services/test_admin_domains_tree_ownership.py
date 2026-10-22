#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The template tree list requires access to its root template."""

from unittest.mock import patch

import pytest
from api.services.admin.domains import AdminDomainsService
from api.services.error import Error

MANAGER = {"user_id": "u-mgr", "category_id": "cat-a", "role_id": "manager"}


class TestTemplateTreeListOwnership:
    @patch("api.services.admin.domains.ApiAdmin.get_template_tree_list")
    @patch(
        "api.services.admin.domains.Helpers.owns_domain_id",
        side_effect=Error("forbidden", "foreign category"),
    )
    def test_refuses_a_template_of_another_category(self, mock_owns, mock_tree):
        with pytest.raises(Error):
            AdminDomainsService.get_template_tree_list(MANAGER, "tpl-foreign")
        mock_owns.assert_called_once_with(MANAGER, "tpl-foreign")
        # The leak is in the root node the builder returns, so it must not
        # even be reached.
        mock_tree.assert_not_called()

    @patch(
        "api.services.admin.domains.ApiAdmin.get_template_tree_list",
        return_value=[{"id": "tpl-own"}],
    )
    @patch("api.services.admin.domains.Helpers.owns_domain_id")
    def test_still_serves_an_owned_template(self, mock_owns, mock_tree):
        assert AdminDomainsService.get_template_tree_list(MANAGER, "tpl-own") == [
            {"id": "tpl-own"}
        ]
        mock_tree.assert_called_once_with("tpl-own", MANAGER["user_id"])
