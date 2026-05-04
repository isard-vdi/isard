#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``Deployment.get_deployment_permissions`` —
unwrap the cached ``{"user_permissions": [...]}`` document and return the
inner list (or ``[]`` for legacy rows missing the field).

Why: the apiv4 GET ``/item/deployment/{id}/permissions`` endpoint and
the PUT ``/item/deployment/{id}/edit`` body both speak the same shape —
``list[DeploymentPermissions]``. The model previously returned the raw
plucked dict, so a legacy deployment row without a ``user_permissions``
field surfaced as ``{}`` on GET; old-frontend stored that and re-sent it
on the edit-form PUT, which then 422'd because ``{}`` is not a list.
"""

from types import SimpleNamespace

import pytest


@pytest.fixture
def patched_caches(monkeypatch):
    from isardvdi_common.models import deployment as mod

    captured = {}

    def fake_get_document(table, item_id, fields):
        captured["args"] = (table, item_id, tuple(fields))
        return captured.get("return", None)

    monkeypatch.setattr(mod.Caches, "get_document", staticmethod(fake_get_document))
    return {"mod": mod, "captured": captured}


def _bound(mod, deployment_id):
    """Bind ``get_deployment_permissions`` to a stand-in instance.

    The real ``Deployment(id)`` constructor talks to RethinkDB to hydrate
    the row; we want to exercise the unwrap branch only, so we bind the
    method to a ``SimpleNamespace`` carrying just ``id``.
    """
    inst = SimpleNamespace(id=deployment_id)
    return mod.Deployment.get_deployment_permissions.__get__(inst)


class TestGetDeploymentPermissions:
    def test_returns_inner_list_when_field_present(self, patched_caches):
        patched_caches["captured"]["return"] = {"user_permissions": ["recreate"]}

        result = _bound(patched_caches["mod"], "dep-1")()

        assert result == ["recreate"]
        assert patched_caches["captured"]["args"] == (
            "deployments",
            "dep-1",
            ("user_permissions",),
        )

    def test_returns_empty_list_when_field_absent(self, patched_caches):
        # Legacy deployment row with no user_permissions field — pluck
        # returns the empty dict; we must surface ``[]`` so the GET
        # contract stays a list and old-frontend's edit-form round-trip
        # passes the PUT body schema.
        patched_caches["captured"]["return"] = {}

        result = _bound(patched_caches["mod"], "dep-1")()

        assert result == []

    def test_returns_empty_list_when_field_explicitly_null(self, patched_caches):
        """The field exists but stores ``None`` (defensive — has surfaced
        on rows touched by half-finished migrations)."""
        patched_caches["captured"]["return"] = {"user_permissions": None}

        result = _bound(patched_caches["mod"], "dep-1")()

        assert result == []

    def test_raises_not_found_when_row_missing(self, patched_caches):
        from isardvdi_common.helpers.error_factory import Error

        patched_caches["captured"]["return"] = None

        with pytest.raises(Error):
            _bound(patched_caches["mod"], "dep-1")()
