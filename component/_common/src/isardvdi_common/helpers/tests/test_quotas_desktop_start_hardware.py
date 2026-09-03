#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Quotas.desktop_start`` checks the hardware the desktop will hold.

The create path has no desktop row yet, so it passes the template it derives
from plus the hardware the user submitted: against the template's own values a
2 GB user could not create a 0.5 GB temporal desktop from a 3.5 GB template.

``check_quota`` runs unmocked — the point is which numbers reach it. The
method is ``@cached`` on ``(user_id, desktop_id, hardware)``, so each test
uses a distinct user id to avoid a cross-test cache hit.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers import quotas as mod
from isardvdi_common.helpers.error_base import ErrorBase

Q = mod.Quotas

# 3.5 GiB and 6 vCPUs, both over the user quota below.
TEMPLATE = {"id": "t-1", "create_dict": {"hardware": {"vcpus": 6, "memory": 3670016}}}


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def env(monkeypatch):
    docs = {
        "domains": TEMPLATE,
        "groups": {"name": "Group 1", "limits": None},
        "categories": {"name": "Cat 1", "limits": None},
    }
    monkeypatch.setattr(
        mod.Caches,
        "get_document",
        classmethod(lambda cls, table, *a, **k: docs[table]),
    )
    monkeypatch.setattr(
        mod.Caches,
        "get_cached_user_with_names",
        classmethod(
            lambda cls, uid: {
                "id": uid,
                "role": "user",
                "group": "grp-1",
                "category": "cat-1",
                "name": "recreate2",
                "group_name": "Group 1",
                "category_name": "Cat 1",
            }
        ),
    )
    monkeypatch.setattr(Q, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(Q), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    tbl = {n: MagicMock(name=f"r.table({n})") for n in ("users", "media")}
    monkeypatch.setattr(mod.r, "table", lambda name: tbl.get(name, MagicMock()))
    tbl[
        "users"
    ].get_all.return_value.eq_join.return_value.sum.return_value.run.return_value = 0
    tbl["media"].get_all.return_value.sum.return_value.run.return_value = 0

    monkeypatch.setattr(
        Q,
        "Get",
        classmethod(
            lambda cls, **kw: {
                "quota": {"running": 1, "memory": 2, "vcpus": 1, "total_size": 50},
                "used": {"running": 0, "memory": 0, "vcpus": 0, "total_size": 0},
            }
        ),
    )
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
    return docs


def test_the_template_hardware_is_what_gets_checked_by_default(env):
    with pytest.raises(ErrorBase) as exc:
        Q.desktop_start("u-default", "t-1")

    assert exc.value.error["description_code"] == "desktop_start_memory_quota_exceeded"


def test_submitted_hardware_replaces_the_template_one(env):
    # 0.5 GiB and 1 vCPU: within a 2 GB / 1 vCPU quota, unlike the template.
    Q.desktop_start("u-submitted", "t-1", hardware={"memory": 524288, "vcpus": 1})


def test_an_override_that_exceeds_the_quota_is_still_refused(env):
    with pytest.raises(ErrorBase) as exc:
        Q.desktop_start("u-toobig", "t-1", hardware={"memory": 3145728, "vcpus": 1})

    assert exc.value.error["description_code"] == "desktop_start_memory_quota_exceeded"


def test_a_partial_override_falls_back_to_the_template(env):
    with pytest.raises(ErrorBase) as exc:
        Q.desktop_start("u-partial", "t-1", hardware={"memory": 524288})

    assert exc.value.error["description_code"] == "desktop_start_vcpu_quota_exceeded"
