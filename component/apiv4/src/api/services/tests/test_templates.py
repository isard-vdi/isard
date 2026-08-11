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


class TestGetTemplateTree:
    """``get_template_tree`` must MERGE the per-root deployment index
    into the tree-wide list that ``check_children`` already computed, never
    overwrite it. The overwrite (``derivates["deployments"] = []``, introduced
    by cea1f0ff1c) hid every deployment hanging off a DERIVED template, which
    is exactly what the delete-confirmation modal failed to show in the field.
    """

    PAYLOAD = {"user_id": "u1", "category_id": "cat-1"}

    def _wire(
        self,
        monkeypatch,
        *,
        check_children,
        index_deployments,
        owns=True,
    ):
        import api.services.templates as mod

        monkeypatch.setattr(
            mod.CommonApiAdmin,
            "get_template_tree_list",
            staticmethod(lambda template_id, user_id: [{"id": template_id}]),
        )
        monkeypatch.setattr(
            mod.CommonTemplates,
            "check_children",
            # fresh dict per call: the service mutates it (pop/append)
            staticmethod(
                lambda payload, tree: {k: v for k, v in check_children.items()}
            ),
        )
        monkeypatch.setattr(
            mod.CommonTemplates,
            "is_duplicate",
            staticmethod(lambda template_id: False),
        )
        monkeypatch.setattr(
            mod.CommonTemplates,
            "get_deployments_with_template",
            staticmethod(
                lambda template_id, return_username=False: list(index_deployments)
            ),
        )
        monkeypatch.setattr(
            mod.CommonTemplates,
            "has_cross_category_derivatives",
            staticmethod(lambda template_id, category_id: False),
        )

        def _owns(payload, deployment_id, check_co_owner=True):
            if not owns:
                raise Exception("not owned")
            return deployment_id

        monkeypatch.setattr(mod.Helpers, "owns_deployment_id", staticmethod(_owns))

    def test_regression_3118_keeps_deployments_from_check_children(self, monkeypatch):
        """The tree walk found 4 deployments (all under derivatives); the
        per-root index finds none. All 4 must survive. This is the test that
        would have prevented the incident."""
        self._wire(
            monkeypatch,
            check_children={
                "domains": [{"id": "root"}],
                "deployments": [
                    {"id": "d1", "kind": "deployment"},
                    {"id": "d2", "kind": "deployment"},
                    {"id": "d3", "kind": "deployment"},
                    {"id": "d4", "kind": "deployment"},
                ],
                "pending": False,
                "deployment_ids": ["d1", "d2", "d3", "d4"],
            },
            index_deployments=[],
        )
        result = TemplateService.get_template_tree("root", self.PAYLOAD)
        assert len(result["deployments"]) == 4

    def test_same_deployment_in_both_sources_appears_once(self, monkeypatch):
        """A deployment that both the tree and the per-root index return must
        be emitted once."""
        self._wire(
            monkeypatch,
            check_children={
                "domains": [{"id": "root"}],
                "deployments": [{"id": "dX", "kind": "deployment"}],
                "pending": False,
                "deployment_ids": ["dX"],
            },
            index_deployments=[{"id": "dX", "name": "n", "username": "u"}],
        )
        result = TemplateService.get_template_tree("root", self.PAYLOAD)
        ids = [d.get("id") for d in result["deployments"]]
        assert ids.count("dX") == 1
        assert len(result["deployments"]) == 1

    def test_unowned_deployment_from_index_is_masked(self, monkeypatch):
        """A deployment found only in the per-root index that the caller does
        not own masks to ``{}`` and sets ``pending``."""
        self._wire(
            monkeypatch,
            check_children={
                "domains": [{"id": "root"}],
                "deployments": [],
                "pending": False,
                "deployment_ids": [],
            },
            index_deployments=[{"id": "dZ", "name": "n", "username": "u"}],
            owns=False,
        )
        result = TemplateService.get_template_tree("root", self.PAYLOAD)
        assert {} in result["deployments"]
        assert result["pending"] is True

    def test_deployment_ids_not_leaked_in_response(self, monkeypatch):
        """``deployment_ids`` is an internal dedup index, not part of
        TemplateTreeResponse; it must be popped before returning."""
        self._wire(
            monkeypatch,
            check_children={
                "domains": [{"id": "root"}],
                "deployments": [{"id": "d1", "kind": "deployment"}],
                "pending": False,
                "deployment_ids": ["d1"],
            },
            index_deployments=[],
        )
        result = TemplateService.get_template_tree("root", self.PAYLOAD)
        assert "deployment_ids" not in result
