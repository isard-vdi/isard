# SPDX-License-Identifier: AGPL-3.0-or-later

"""Business-precondition guards of ``TemplateService`` (services/templates.py).

* ``delete_template`` -- a manager may not delete a template with derivatives in
  OTHER categories (forbidden); same-category / admin proceed to the delete.
* ``get_template_allowed`` / ``update_template_allowed`` -- unknown template ->
  not_found.
* ``duplicate_template`` -- an owner picked in the request owns the copy, only
  when the caller owns that user; an unknown owner -> not_found.

The real method decides; only the models / Common layer are stubbed. Asserts
``Error`` type / ``description_code``.
"""

from unittest.mock import patch

import pytest
from api.services.error import Error
from api.services.templates import TemplateService
from isardvdi_common.helpers.error_base import ErrorBase


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


class TestDuplicateTemplate:
    ADMIN = {"role_id": "admin", "category_id": "cat-a", "user_id": "admin"}
    DATA = {
        "name": "Copy",
        "description": "",
        "allowed": {},
        "enabled": True,
        "user_id": None,
    }

    @pytest.fixture
    def common(self):
        with (
            patch("api.services.templates.CommonTemplates.get_template"),
            patch("api.services.templates.CommonTemplates.check_template_status"),
            patch(
                "api.services.templates.Helpers.check_user_duplicated_domain_name"
            ) as name_check,
            patch(
                "api.services.templates.CommonTemplates.duplicate_template",
                return_value="t-copy",
            ) as dup,
            patch("api.services.templates.clear_templates_cache"),
        ):
            yield name_check, dup

    def test_duplicates_for_the_selected_owner(self, common):
        name_check, dup = common
        owner = {"user_id": "u2", "role_id": "user", "category_id": "cat-b"}
        with (
            patch("api.services.templates.RethinkUser.exists", return_value=True),
            patch("api.services.templates.Quotas.template_create") as quota,
            patch(
                "api.services.templates.Helpers.gen_payload_from_user",
                return_value=owner,
            ),
        ):
            result = TemplateService.duplicate_template(
                self.ADMIN, "t1", {**self.DATA, "user_id": "u2"}
            )
        assert result == "t-copy"
        quota.assert_called_once_with("u2")
        assert name_check.call_args.kwargs["user_id"] == "u2"
        assert dup.call_args.args[0] == owner

    def test_without_owner_keeps_the_requester(self, common):
        name_check, dup = common
        with patch("api.services.templates.Helpers.gen_payload_from_user") as gen:
            TemplateService.duplicate_template(self.ADMIN, "t1", self.DATA)
        gen.assert_not_called()
        assert name_check.call_args.kwargs["user_id"] == "admin"
        assert dup.call_args.args[0] is self.ADMIN

    def test_manager_cannot_duplicate_for_another_category(self, common):
        _, dup = common
        manager = {"role_id": "manager", "category_id": "cat-a", "user_id": "m"}
        with patch(
            "isardvdi_common.helpers.helpers.Caches.get_document",
            return_value={"category": "cat-b", "role": "user"},
        ):
            with pytest.raises(ErrorBase) as exc:
                TemplateService.duplicate_template(
                    manager, "t1", {**self.DATA, "user_id": "u2"}
                )
        assert exc.value.error["error"] == "forbidden"
        dup.assert_not_called()

    def test_unknown_owner_not_found(self, common):
        _, dup = common
        with patch("api.services.templates.RethinkUser.exists", return_value=False):
            with pytest.raises(Error) as exc:
                TemplateService.duplicate_template(
                    self.ADMIN, "t1", {**self.DATA, "user_id": "ghost"}
                )
        assert exc.value.error["error"] == "not_found"
        dup.assert_not_called()


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
