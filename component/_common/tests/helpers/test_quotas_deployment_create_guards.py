#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``Quotas.deployment_create`` — the new-deployment gate.

Creating a deployment for a set of target users checks the per-group and
per-category desktop limits: the count of desktops that already exist plus
the users being added must not exceed the limit. The gates pinned:

* group desktop limit would be exceeded    (L1277) deployment_desktop_new_group_limit_exceeded
* category desktop limit would be exceeded (L1302) deployment_desktop_new_category_limit_exceeded
* within both limits -> passes (returns None)

``deployment_create`` runs unmocked; the owner lookup, the group/category
documents, the deployment/domain rethink counts and the
``check_field_quotas*`` collaborators are stubbed. The limit comparison
itself (``existing + added > limit``) is taken by the real code.

``ErrorBase`` — see ``test_quotas_validators`` — matches the raised instance.
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


def _owner():
    return {
        "id": "owner-1",
        "name": "Owner",
        "group": "grp-1",
        "category": "cat-1",
        "group_name": "Group 1",
    }


def _target_user():
    return {"id": "u-1", "group": "grp-1", "category": "cat-1"}


@pytest.fixture
def env(monkeypatch):
    """Stub owner/doc lookups, rethink counts and the field-quota collabs.

    ``docs`` answers ``get_document`` for the group/category the target
    users belong to; ``domain_count`` is the existing-desktops count the
    limit compares against.
    """
    docs = {
        "groups": {"name": "Group 1", "limits": None},
        "categories": {"name": "Cat 1", "limits": None},
    }

    monkeypatch.setattr(
        mod.Caches,
        "get_cached_user_with_names",
        classmethod(lambda cls, uid: _owner()),
    )
    monkeypatch.setattr(
        mod.Caches,
        "get_document",
        classmethod(lambda cls, table, *a, **k: docs[table]),
    )
    monkeypatch.setattr(Q, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(Q), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    tbl = {n: MagicMock(name=f"r.table({n})") for n in ("deployments", "domains")}
    monkeypatch.setattr(mod.r, "table", lambda name: tbl.get(name, MagicMock()))
    # existing desktop count the group/category limit compares against
    tbl["domains"].get_all.return_value.count.return_value.run.return_value = 5

    # field-quota collaborators: no-ops (their own gate is tested elsewhere)
    monkeypatch.setattr(
        Q, "check_field_quotas_and_limits", classmethod(lambda cls, *a, **k: None)
    )
    monkeypatch.setattr(Q, "check_field_quotas", classmethod(lambda cls, *a, **k: None))
    return {"docs": docs}


class TestDeploymentCreateGuards:
    def test_group_desktop_limit_exceeded(self, env):
        # 5 existing + 1 added > group limit of 1 -> reject on the group axis.
        env["docs"]["groups"] = {"name": "Group 1", "limits": {"desktops": 1}}
        with pytest.raises(ErrorBase) as exc:
            Q.deployment_create("owner-1", users=[_target_user()])
        assert (
            exc.value.error["description_code"]
            == "deployment_desktop_new_group_limit_exceeded"
        )

    def test_category_desktop_limit_exceeded(self, env):
        # Group has no limits (its loop body is skipped), category limit of 1
        # is exceeded -> reject on the category axis.
        env["docs"]["groups"] = {"name": "Group 1", "limits": None}
        env["docs"]["categories"] = {"name": "Cat 1", "limits": {"desktops": 1}}
        with pytest.raises(ErrorBase) as exc:
            Q.deployment_create("owner-1", users=[_target_user()])
        assert (
            exc.value.error["description_code"]
            == "deployment_desktop_new_category_limit_exceeded"
        )

    def test_within_limits_passes(self, env):
        env["docs"]["groups"] = {"name": "Group 1", "limits": {"desktops": 100}}
        env["docs"]["categories"] = {"name": "Cat 1", "limits": {"desktops": 100}}
        assert Q.deployment_create("owner-1", users=[_target_user()]) is None
