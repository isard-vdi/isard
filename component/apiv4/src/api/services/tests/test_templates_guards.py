# SPDX-License-Identifier: AGPL-3.0-or-later

"""Business-precondition guards of ``TemplateService`` (services/templates.py).

* ``delete_template`` -- a manager may not delete a template with derivatives in
  OTHER categories (forbidden); same-category / admin proceed to the delete.
* ``get_template_allowed`` / ``update_template_allowed`` -- unknown template ->
  not_found.

The real method decides; only the models / Common layer are stubbed. Asserts
``Error`` type / ``description_code``.
"""

from unittest.mock import patch

import pytest
from api.services.error import Error
from api.services.templates import TemplateService


class TestDeleteTemplate:
    def test_manager_cross_category_derivatives_forbidden(self):
        with (
            patch(
                "api.services.templates.CommonTemplates.list_derivative_categories",
                return_value=[{"category": "other-cat"}],
            ),
            patch("api.services.templates.DesktopEvents.templates_delete") as td,
        ):
            with pytest.raises(Error) as exc:
                TemplateService.delete_template(
                    {"role_id": "manager", "category_id": "cat-a", "user_id": "m"},
                    "t1",
                )
        assert (
            exc.value.error["description_code"] == "template_cross_category_derivatives"
        )
        td.assert_not_called()  # nothing deleted when blocked

    def test_manager_same_category_derivatives_proceeds(self):
        with (
            patch(
                "api.services.templates.CommonTemplates.list_derivative_categories",
                return_value=[{"category": "cat-a"}],
            ),
            patch(
                "api.services.templates.DesktopEvents.templates_delete",
                return_value={"ok": True},
            ) as td,
            patch("api.services.templates.clear_templates_cache"),
        ):
            result = TemplateService.delete_template(
                {"role_id": "manager", "category_id": "cat-a", "user_id": "m"}, "t1"
            )
        assert result == {"ok": True}
        td.assert_called_once()

    def test_admin_bypasses_cross_category_check(self):
        with (
            patch(
                "api.services.templates.CommonTemplates.list_derivative_categories"
            ) as lst,
            patch(
                "api.services.templates.DesktopEvents.templates_delete",
                return_value={"ok": True},
            ) as td,
            patch("api.services.templates.clear_templates_cache"),
        ):
            TemplateService.delete_template(
                {"role_id": "admin", "category_id": "cat-a", "user_id": "a"}, "t1"
            )
        # Admin never even consults the cross-category derivative list.
        lst.assert_not_called()
        td.assert_called_once()


class TestTemplateAllowedNotFound:
    @patch("api.services.templates.RethinkDomain.exists", return_value=False)
    def test_get_allowed_unknown_template_not_found(self, _exists):
        with pytest.raises(Error) as exc:
            TemplateService.get_template_allowed("ghost", "cat-a")
        assert exc.value.error["error"] == "not_found"

    @patch("api.services.templates.RethinkDomain.exists", return_value=False)
    def test_update_allowed_unknown_template_not_found(self, _exists):
        with pytest.raises(Error) as exc:
            TemplateService.update_template_allowed("ghost", {})
        assert exc.value.error["error"] == "not_found"
