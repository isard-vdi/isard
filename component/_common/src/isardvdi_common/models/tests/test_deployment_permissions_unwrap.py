#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``Deployment.get_deployment_permissions``.

The model calls ``Caches.get_document(table, id, ["user_permissions"])``.
``Caches.get_document`` with a single ``keys`` element returns the
*unwrapped* field value directly (cf. ``caches.py``::

    if len(keys) == 1:
        return copy.deepcopy(data.get(keys[0], None))

) — NOT a row dict. The earlier implementation tried
``users_permissions.get("user_permissions")`` and crashed with
``AttributeError`` on every production row that actually had a list
(Naomi #15178/#50).

The current contract is: the method returns ``[]`` whenever the cache
returns None, an empty list, or any falsy value, and returns the list
itself when the cache returns a list of permission entries.
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
    def test_returns_list_when_cache_returns_list(self, patched_caches):
        # Real cache behaviour: with a single ``keys`` element it
        # returns the unwrapped field value directly.
        patched_caches["captured"]["return"] = ["recreate"]

        result = _bound(patched_caches["mod"], "dep-1")()

        assert result == ["recreate"]
        assert patched_caches["captured"]["args"] == (
            "deployments",
            "dep-1",
            ("user_permissions",),
        )

    def test_returns_empty_list_when_cache_returns_none(self, patched_caches):
        # Cache returns None for either a row that doesn't exist or a
        # row whose user_permissions field is missing/null. Both
        # collapse to [].
        patched_caches["captured"]["return"] = None

        result = _bound(patched_caches["mod"], "dep-1")()

        assert result == []

    def test_returns_empty_list_when_cache_returns_empty_list(self, patched_caches):
        patched_caches["captured"]["return"] = []

        result = _bound(patched_caches["mod"], "dep-1")()

        assert result == []
