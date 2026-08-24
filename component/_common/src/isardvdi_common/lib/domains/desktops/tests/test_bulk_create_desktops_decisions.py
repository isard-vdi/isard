#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Decisions inside ``DesktopsProcessed.bulk_create_desktops``.

The two entry guards (template-not-found, no-targets-selected) are pinned
elsewhere. This file targets the *decisions* in the target-user resolution —
not one test per branch, since most of that body is iteration. The three that
actually change who gets a desktop:

* selecting targets by **role** / **category** is admin-only (L1351): a
  manager's role selection resolves nobody;
* a **manager** resolving an empty group selection is scoped to their own
  category (``index="parent_category"``, L1388) — not the whole system;
* the resolved user set is **de-duplicated** (L1424): a user hit by two
  selectors is created once.

The per-user create loop (L1432-1460) is pure iteration — one
``new_from_template`` per resolved user — and is intentionally NOT unit
tested here; it carries no decision of its own.

``bulk_create_desktops`` runs unmocked; the template lookup, the quota
limiter, the per-user collaborators, the schema and ``new_from_template``
are stubbed, and the rethink resolution is a per-table mock.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.lib.domains.desktops import desktops as mod

DP = mod.DesktopsProcessed


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _selected(roles=False, categories=False, groups=False, users=False):
    return {
        "roles": roles,
        "categories": categories,
        "groups": groups,
        "users": users,
    }


def _payload(role_id="admin"):
    return {"role_id": role_id, "category_id": "cat-1", "group_id": "grp-1"}


def _data(selected):
    return {
        "allowed": selected,
        "template_id": "tmpl-1",
        "name": "bulk",
        "description": "bulk desc",
    }


@pytest.fixture
def env(monkeypatch):
    """Stub template/quota/collaborators + a per-table rethink mock.

    ``tbl`` maps table -> its ``r.table`` mock; ``nft`` is the
    ``new_from_template`` spy tests assert against.
    """
    template = {
        "id": "tmpl-1",
        "create_dict": {"hardware": {"interfaces": []}},
        "guest_properties": {},
        "image": None,
    }
    monkeypatch.setattr(
        mod.Caches, "get_document", classmethod(lambda cls, t, d: template)
    )
    monkeypatch.setattr(
        mod.Quotas,
        "limit_user_hardware_allowed",
        staticmethod(lambda payload, cd: cd),
    )
    monkeypatch.setattr(
        mod.Helpers,
        "check_user_duplicated_domain_name",
        classmethod(lambda cls, name, uid: None),
    )
    monkeypatch.setattr(
        mod.Quotas, "desktop_create", classmethod(lambda cls, uid: None)
    )

    class _Schema:
        def __init__(self, **kw):
            self._kw = kw

        def model_dump(self):
            return {**self._kw, "id": "gen-id"}

    monkeypatch.setattr(mod, "BulkDesktopFromTemplate", _Schema)

    monkeypatch.setattr(DP, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(DP), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    tbl = {}
    monkeypatch.setattr(
        mod.r,
        "table",
        lambda name: tbl.setdefault(name, MagicMock(name=f"r.table({name})")),
    )
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", x))

    nft = MagicMock(name="new_from_template")
    monkeypatch.setattr(
        DP, "new_from_template", classmethod(lambda cls, *a, **k: nft(*a, **k))
    )
    return {"tbl": tbl, "nft": nft}


class TestBulkCreateDesktopsDecisions:
    def test_role_selection_is_admin_only(self, env):
        # A manager selecting by role resolves NOBODY -> nothing created.
        # The role->users query is armed with a real user so that dropping the
        # admin gate would resolve it (and this test would catch that).
        users_tbl = env["tbl"].setdefault("users", MagicMock())
        users_tbl.get_all.return_value.filter.return_value.__getitem__.return_value.run.return_value = [
            "u-mgr"
        ]
        data = _data(_selected(roles=["r-1"]))
        result = DP.bulk_create_desktops(_payload(role_id="manager"), data)
        assert result == []
        env["nft"].assert_not_called()

    def test_admin_role_selection_resolves_users(self, env):
        # Same selection as admin does resolve users and create desktops.
        users_tbl = env["tbl"].setdefault("users", MagicMock())
        users_tbl.get_all.return_value.filter.return_value.__getitem__.return_value.run.return_value = [
            "u-9"
        ]
        result = DP.bulk_create_desktops(
            _payload(role_id="admin"), _data(_selected(roles=["r-1"]))
        )
        assert [d["user"] for d in result] == ["u-9"]
        env["nft"].assert_called_once()

    def test_manager_group_resolution_scoped_to_own_category(self, env):
        # An empty group selection for a manager must query groups by
        # parent_category = the manager's category, not the whole system.
        groups = env["tbl"].setdefault("groups", MagicMock())
        groups.get_all.return_value.__getitem__.return_value.run.return_value = ["g-1"]
        users = env["tbl"].setdefault("users", MagicMock())
        users.get_all.return_value.filter.return_value.__getitem__.return_value.run.return_value = [
            "u-1"
        ]

        DP.bulk_create_desktops(
            _payload(role_id="manager"), _data(_selected(groups=[]))
        )

        groups.get_all.assert_called_once_with("cat-1", index="parent_category")

    def test_duplicate_users_are_created_once(self, env):
        # A user hit twice (here via a duplicated explicit selection) yields a
        # single desktop — the resolved set is de-duplicated.
        result = DP.bulk_create_desktops(
            _payload(role_id="admin"), _data(_selected(users=["u-1", "u-1"]))
        )
        assert [d["user"] for d in result] == ["u-1"]
        env["nft"].assert_called_once()
