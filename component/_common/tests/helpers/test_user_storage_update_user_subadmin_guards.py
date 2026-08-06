#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``UserStorage.user_storage_update_user_subadmin``.

Keeps a user's provider-side subadmin memberships in sync with their role.
Pinned:

* no provider configured -> silent return, nothing enqueued (L1738-1740);
* ``role == "admin"`` -> enqueue adds for every category+group the user is
  not already subadmin of (L1744), honouring the membership check (L1747);
* a non-admin/non-manager role -> enqueue deletes for all their subadmin
  groups (L1768).

The method runs unmocked; the provider lookup, the provider connection and
the batch-enqueue collaborators are stubbed, so the add/delete decision is
taken by the real code and asserted via what it enqueues.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers import user_storage as mod

US = mod.UserStorage


def _provider(subadmin, access=None):
    conn = MagicMock(name="conn")
    conn.get_user.return_value = {"subadmin": list(subadmin)}
    return {"conn": conn, "cfg": {"access": access if access is not None else []}}


@pytest.fixture
def env(monkeypatch):
    """Stub provider lookup + category/group listings + batch enqueuers.

    ``state["provider"]`` is what ``_get_provider`` returns; tests set it.
    """
    state = {"provider": _provider([])}
    monkeypatch.setattr(
        US, "_get_provider", classmethod(lambda cls, pid: state["provider"])
    )
    monkeypatch.setattr(
        US, "_get_provider_categories", classmethod(lambda cls, pid: ["cat-1"])
    )
    monkeypatch.setattr(
        US, "_get_provider_groups", classmethod(lambda cls, pid: ["grp-1"])
    )
    monkeypatch.setattr(
        US, "_get_isard_user_category_id", classmethod(lambda cls, uid: "cat-1")
    )
    add = MagicMock(name="add_subadmin_batches")
    delete = MagicMock(name="delete_subadmin_batches")
    monkeypatch.setattr(
        US,
        "process_user_storage_add_user_subadmin_batches",
        classmethod(lambda cls, groups, pid: add(groups, pid)),
    )
    monkeypatch.setattr(
        US,
        "process_user_storage_delete_subadmin_batches",
        classmethod(lambda cls, groups, pid: delete(groups, pid)),
    )
    return {"state": state, "add": add, "delete": delete}


class TestUpdateUserSubadminGuards:
    def test_no_provider_returns_silently(self, env):
        env["state"]["provider"] = None
        assert US.user_storage_update_user_subadmin("u-1", "admin", "p-1") is None
        env["add"].assert_not_called()
        env["delete"].assert_not_called()

    def test_admin_adds_all_missing_groups(self, env):
        env["state"]["provider"] = _provider(subadmin=[])
        US.user_storage_update_user_subadmin("u-1", "admin", "p-1")
        env["add"].assert_called_once()
        assert env["add"].call_args.args[0] == [["u-1", "cat-1"], ["u-1", "grp-1"]]
        env["delete"].assert_not_called()

    def test_admin_skips_groups_already_subadmin(self, env):
        # cat-1 already in the user's subadmin set -> only grp-1 is added.
        env["state"]["provider"] = _provider(subadmin=["cat-1"])
        US.user_storage_update_user_subadmin("u-1", "admin", "p-1")
        assert env["add"].call_args.args[0] == [["u-1", "grp-1"]]

    def test_non_privileged_role_removes_all_subadmin(self, env):
        env["state"]["provider"] = _provider(subadmin=["cat-1", "grp-1"])
        US.user_storage_update_user_subadmin("u-1", "viewer", "p-1")
        env["delete"].assert_called_once()
        assert env["delete"].call_args.args[0] == [["u-1", "cat-1"], ["u-1", "grp-1"]]
        env["add"].assert_not_called()
