#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``Quotas.check_users_group_quota`` — the group-move gate.

Before a set of users is moved into a group, this checks that none of them
would blow the group's (or, when the group defers, the category's) quota.
The gates pinned:

* group quota unset -> fall back to the category quota   (L1842)
* neither quota nor limits set -> nothing to check, return early (L1869)
* a user over the resolved quota is rejected             (L1878) quota_exceeded

``check_users_group_quota`` runs unmocked; the rethink lookups
(``groups`` / ``categories``) and the per-user ``Get`` snapshot are stubbed
so the comparison itself is taken by the real code.

``ErrorBase`` — see ``test_quotas_validators`` — matches the raised instance
regardless of how ``error_factory`` resolves in this process.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers import quotas as mod
from isardvdi_common.helpers.error_base import ErrorBase

Q = mod.Quotas


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def rdb(monkeypatch):
    """Stub the rethink boundary; ``tbl`` maps table -> its ``r.table`` mock."""
    monkeypatch.setattr(Q, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(Q), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    tbl = {n: MagicMock(name=f"r.table({n})") for n in ("groups", "categories")}
    monkeypatch.setattr(mod.r, "table", lambda name: tbl[name])
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", x))
    # process_group_limits short-circuits to False by default (no group-limit pass)
    monkeypatch.setattr(
        mod.QuotasProcess, "process_group_limits", classmethod(lambda cls, gid: False)
    )
    return tbl


def _group(quota, limits):
    return {
        "name": "the-group",
        "quota": quota,
        "limits": limits,
        "parent_category": "cat-1",
    }


class TestCheckUsersGroupQuotaGuards:
    def test_returns_early_when_no_quota_and_no_limits(self, rdb, monkeypatch):
        # Group defers, category also has neither quota nor limits -> nothing
        # to enforce; the per-user snapshot must never be consulted.
        rdb["groups"].get.return_value.pluck.return_value.run.return_value = _group(
            False, False
        )
        rdb["categories"].get.return_value.pluck.return_value.run.return_value = {}
        get = MagicMock(name="Get")
        monkeypatch.setattr(Q, "Get", classmethod(lambda cls, **kw: get(**kw)))

        assert Q.check_users_group_quota(["u-1"], "grp-1") is None
        get.assert_not_called()

    def test_group_quota_defers_to_category_and_user_over_quota_is_rejected(
        self, rdb, monkeypatch
    ):
        # Group carries no quota -> resolve the category quota (vcpus<=2);
        # a user using 5 vcpus must be rejected as quota_exceeded.
        rdb["groups"].get.return_value.pluck.return_value.run.return_value = _group(
            False, {"running": 100}
        )
        rdb["categories"].get.return_value.pluck.return_value.run.return_value = {
            "quota": {"vcpus": 2}
        }
        monkeypatch.setattr(
            Q,
            "Get",
            classmethod(lambda cls, **kw: {"used": {"vcpus": 5}}),
        )

        with pytest.raises(ErrorBase) as exc:
            Q.check_users_group_quota(["u-over"], "grp-1")
        assert exc.value.error["description_code"] == "quota_exceeded"

    def test_user_under_resolved_quota_passes(self, rdb, monkeypatch):
        # Same fallback, but 1 vcpu is within the category quota -> no raise.
        rdb["groups"].get.return_value.pluck.return_value.run.return_value = _group(
            False, {"running": 100}
        )
        rdb["categories"].get.return_value.pluck.return_value.run.return_value = {
            "quota": {"vcpus": 2}
        }
        monkeypatch.setattr(
            Q,
            "Get",
            classmethod(lambda cls, **kw: {"used": {"vcpus": 1}}),
        )

        assert Q.check_users_group_quota(["u-ok"], "grp-1") is None
