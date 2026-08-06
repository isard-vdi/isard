#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``Quotas.deployment_desktop_start`` — the deployment-start gate.

Starting a deployment desktop is quota/limit-checked unless the desktop is
not part of a deployment (reject) or the requester is an admin (bypass).
The gates pinned:

* the desktop is not part of a deployment -> reject   (L980) precondition_required
* an admin bypasses every quota/limit check           (L983)
* a non-admin whose group defines limits runs the group ``check_limits`` pass (L1004)

``deployment_desktop_start`` runs unmocked; the document lookups, the
``check_field_quotas`` / ``check_limits`` collaborators, the started-desktop
counters and the rethink disk/media sums are stubbed. The decision of
*which* path is taken is left to the real code, and asserted via which
collaborators it does / does not call.

The method is ``@cached`` on ``(user_id, desktop_id)``, so each test uses a
distinct id pair to avoid a cross-test cache hit.
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


def _user(role="advanced"):
    return {
        "id": "u-1",
        "role": role,
        "group": "grp-1",
        "category": "cat-1",
        "name": "Alice",
        "group_name": "Group 1",
        "category_name": "Cat 1",
    }


def _desktop(tag="dep-1"):
    return {
        "id": "d-1",
        "tag": tag,
        "create_dict": {"hardware": {"vcpus": 2, "memory": 2097152}},
    }


@pytest.fixture
def env(monkeypatch):
    """Wire the document lookups + rethink boundary; tests set docs/collabs.

    ``docs`` answers ``Caches.get_document(table, ...)``; ``user`` answers
    ``get_cached_user_with_names``. Both start on a happy non-admin path
    with no group/category limits.
    """
    docs = {
        "domains": _desktop(),
        "groups": {"name": "Group 1", "limits": None},
        "categories": {"name": "Cat 1", "limits": None},
    }
    state = {"user": _user()}

    monkeypatch.setattr(
        mod.Caches,
        "get_document",
        classmethod(lambda cls, table, *a, **k: docs[table]),
    )
    monkeypatch.setattr(
        mod.Caches,
        "get_cached_user_with_names",
        classmethod(lambda cls, uid: state["user"]),
    )
    monkeypatch.setattr(Q, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(Q), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    tbl = {n: MagicMock(name=f"r.table({n})") for n in ("users", "media", "domains")}
    # unknown tables (e.g. "storage" used only as an eq_join argument) get a
    # throwaway mock instead of a KeyError
    monkeypatch.setattr(mod.r, "table", lambda name: tbl.get(name, MagicMock()))
    # disk/media sums -> real numbers so the GB arithmetic works
    tbl[
        "users"
    ].get_all.return_value.eq_join.return_value.sum.return_value.run.return_value = 0
    tbl["media"].get_all.return_value.sum.return_value.run.return_value = 0

    monkeypatch.setattr(Q, "Get", classmethod(lambda cls, **kw: {"used": {}}))
    monkeypatch.setattr(
        Q,
        "get_started_desktops",
        classmethod(
            lambda cls, qid, qidx, owner_only=False: {
                "count": 0,
                "vcpus": 0,
                "memory": 0,
            }
        ),
    )
    field_quotas = MagicMock(name="check_field_quotas")
    limits = MagicMock(name="check_limits")
    monkeypatch.setattr(
        Q, "check_field_quotas", classmethod(lambda cls, *a, **k: field_quotas(*a, **k))
    )
    monkeypatch.setattr(Q, "check_limits", classmethod(lambda cls, **k: limits(**k)))
    return {
        "docs": docs,
        "state": state,
        "field_quotas": field_quotas,
        "limits": limits,
    }


class TestDeploymentDesktopStartGuards:
    def test_not_part_of_deployment_raises(self, env):
        env["docs"]["domains"] = _desktop(tag=False)
        with pytest.raises(ErrorBase) as exc:
            Q.deployment_desktop_start("u-notag", "d-notag")
        assert exc.value.error["error"] == "precondition_required"
        env["field_quotas"].assert_not_called()

    def test_admin_bypasses_all_checks(self, env):
        env["state"]["user"] = _user(role="admin")
        result = Q.deployment_desktop_start("u-admin", "d-admin")
        assert result == env["docs"]["domains"]
        env["field_quotas"].assert_not_called()
        env["limits"].assert_not_called()

    def test_non_admin_no_limits_checks_field_quota_only(self, env):
        result = Q.deployment_desktop_start("u-nolim", "d-nolim")
        assert result == env["docs"]["domains"]
        # the per-user deployment-start quota is checked...
        env["field_quotas"].assert_called_once()
        assert env["field_quotas"].call_args.args[1] == "started_deployment_desktops"
        # ...but with no group/category limits, no limit pass runs
        env["limits"].assert_not_called()

    def test_non_admin_group_limits_run_check_limits(self, env):
        env["docs"]["groups"] = {"name": "Group 1", "limits": {"running": 100}}
        Q.deployment_desktop_start("u-grp", "d-grp")
        env["field_quotas"].assert_called_once()
        # group limit pass ran: running/memory/vcpus/total_size checks
        keys = [c.kwargs["quota_key"] for c in env["limits"].call_args_list]
        assert "running" in keys and "memory" in keys and "vcpus" in keys
