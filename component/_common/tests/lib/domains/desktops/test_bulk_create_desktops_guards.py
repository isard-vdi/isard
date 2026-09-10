#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Precondition guards on ``DesktopsProcessed.bulk_create_desktops``.

Bulk create fans a template out to a set of target users. Two gates run
before any user resolution / DB fan-out and are cheap to pin:

* the source template must exist                (L1355) -> not_found
* at least one target selector must be set      (L1363) -> precondition_required

If the "no targets selected" gate stops firing, an admin who submits an
empty selection silently creates nothing (or, worse downstream, iterates
an unintended user set) — so it is pinned to its ``Error`` type.

``bulk_create_desktops`` runs unmocked; only ``Caches.get_document`` and
the quota limiter it calls before the guards are stubbed.
"""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktops as mod

DP = mod.DesktopsProcessed


def _payload():
    return {"role_id": "admin", "category_id": "cat-1", "group_id": "grp-1"}


def _data(allowed):
    return {
        "template_id": "tmpl-1",
        "name": "bulk-desktop",
        "description": "bulk",
        "allowed": allowed,
    }


_NONE_SELECTED = {"roles": False, "categories": False, "groups": False, "users": False}


class TestBulkCreateDesktopsGuards:
    def test_template_not_found(self, monkeypatch):
        monkeypatch.setattr(
            mod.Caches, "get_document", classmethod(lambda cls, *a, **k: None)
        )
        with pytest.raises(Error) as exc:
            DP.bulk_create_desktops(_payload(), _data(_NONE_SELECTED))
        assert exc.value.error["error"] == "not_found"

    def test_no_target_users_selected(self, monkeypatch):
        # Template resolves and hardware is limited fine, but every target
        # selector is False -> nothing to create -> reject.
        monkeypatch.setattr(
            mod.Caches,
            "get_document",
            classmethod(lambda cls, *a, **k: {"create_dict": {"hardware": {}}}),
        )
        monkeypatch.setattr(
            mod.Quotas,
            "limit_user_hardware_allowed",
            classmethod(lambda cls, payload, cd: cd),
        )
        with pytest.raises(Error) as exc:
            DP.bulk_create_desktops(_payload(), _data(dict(_NONE_SELECTED)))
        assert exc.value.error["error"] == "precondition_required"
