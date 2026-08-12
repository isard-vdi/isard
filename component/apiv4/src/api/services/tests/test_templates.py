# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for TemplateService — façade over CommonTemplates and
RethinkDomain. Tests pin the not-found dispatch + the pagination
plumbing.
"""

from unittest.mock import patch

import pytest
from api.services.error import Error
from api.services.templates import TemplateService


class TestGetAllTemplates:
    @patch(
        "api.services.templates.CommonTemplates.get_template_with_user_info",
        return_value=[{"id": "t1"}],
    )
    def test_returns_helper_value(self, mock_get):
        # Note: get_all_templates is cached with TTLCache; clear cache to
        # avoid bleed between test files.
        TemplateService.get_all_templates.cache_clear()
        assert TemplateService.get_all_templates() == [{"id": "t1"}]
        mock_get.assert_called_once_with()


class TestGetUserTemplates:
    @patch(
        "api.services.templates.CommonTemplates.get_user_templates",
        return_value=[{"id": "t1"}],
    )
    def test_passes_user_id(self, mock_get):
        TemplateService.get_user_templates("u1")
        mock_get.assert_called_once_with("u1")


class TestGetUserTemplatesPaginated:
    @patch("api.services.templates.RethinkDomain.query_count_raw", return_value=12)
    @patch(
        "api.services.templates.RethinkDomain.get_templates",
        return_value=[{"id": "t1"}, {"id": "t2"}],
    )
    @patch("api.services.templates.RethinkUser.exists", return_value=True)
    def test_returns_rows_and_total(self, _exists, mock_rows, mock_count):
        result = TemplateService.get_user_templates_paginated("u1")
        assert result["rows"] == [{"id": "t1"}, {"id": "t2"}]
        assert result["total"] == 12

    @patch("api.services.templates.RethinkUser.exists", return_value=False)
    def test_raises_not_found_for_missing_user(self, _exists):
        with pytest.raises(Error):
            TemplateService.get_user_templates_paginated("ghost")


class TestGetUserAllowedTemplatesFlat:
    @patch("api.services.templates.RethinkUser.exists", return_value=False)
    def test_raises_not_found_for_missing_user(self, _exists):
        with pytest.raises(Error):
            TemplateService.get_user_allowed_templates_flat({"user_id": "ghost"}, "all")


class TestGetUserSharedTemplates:
    """The "shared with me" list must not contain the caller's own
    templates. ``only_in_allowed`` forwards ``ignore_role``, which skips
    the ownership short-circuit in ``is_allowed`` — so an own template
    still enters through its own ACL whenever that ACL matches the
    caller. Only ``exclude_owner_user_id`` keeps it out, which is what
    the media sibling has always done."""

    @patch("api.services.templates.Alloweds.get_items_allowed", return_value=[])
    @patch("api.services.templates.RethinkUser.exists", return_value=True)
    def test_excludes_the_caller_own_templates(self, _exists, mock_alloweds):
        TemplateService.get_user_shared_templates({"user_id": "u1"})
        kwargs = mock_alloweds.call_args.kwargs
        assert kwargs["exclude_owner_user_id"] == "u1"
        assert kwargs["only_in_allowed"] is True

    @patch("api.services.templates.RethinkUser.exists", return_value=False)
    def test_raises_not_found_for_missing_user(self, _exists):
        with pytest.raises(Error):
            TemplateService.get_user_shared_templates({"user_id": "ghost"})


class TestGetUserAllowedTemplatesSortField:
    """``index`` used to be bound only inside ``if sort_field ==
    "accessed"``, so any other value raised UnboundLocalError. The route
    pins the literal, but the service is callable directly."""

    @patch("api.services.templates.RethinkUser.exists", return_value=True)
    def test_unsupported_sort_field_raises_typed_error(self, _exists):
        with pytest.raises(Error):
            TemplateService.get_user_allowed_templates(
                user_id="u1",
                user_category="cat",
                user_group="grp",
                user_role="advanced",
                sort_field="name",
            )
