#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``Quotas.user_hardware_allowed`` — the hardware-permission gate.

This is the door that decides which hardware a payload may see/attach. A
guard that stops firing here does not error: a user simply gets offered
hardware they should not have. The gates pinned:

* an unknown ``kind`` is rejected           (L1624 -> L1638) bad_request
* a missing ``domain_id`` row is rejected    (L1648 -> L1649) not_found
* the admin/manager branch                   (L1662) exposes ``virtualization_nested``

``user_hardware_allowed`` runs unmocked; only the rethink layer and
``get_applied_quota`` (reached on the ``kind="quota"`` fast path, which
skips every ``Alloweds`` lookup) are stubbed. The method is
``@cached`` on ``(user_id, kind, domain_id)`` — role is *not* in the key
— so each test uses a distinct ``user_id`` to avoid a cross-test cache hit.

``ErrorBase`` — not ``error_factory.Error`` — because the factory resolves
lazily to either ``ErrorBase`` or apiv4's subclass and does not cache the
fallback; ``ErrorBase`` matches the instance production actually raises here.
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


def _payload(role_id="advanced", user_id="u-1"):
    return {
        "user_id": user_id,
        "role_id": role_id,
        "category_id": "cat-1",
        "group_id": "grp-1",
    }


@pytest.fixture
def rdb(monkeypatch):
    """Stub the rethink boundary; return the domains-table mock to tweak."""
    monkeypatch.setattr(Q, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(Q), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    domains = MagicMock(name="r.table(domains)")
    monkeypatch.setattr(mod.r, "table", lambda name: {"domains": domains}[name])
    monkeypatch.setattr(
        Q, "get_applied_quota", classmethod(lambda cls, uid: {"quota": {"vcpus": 4}})
    )
    return domains


class TestUserHardwareAllowedGuards:
    def test_kind_not_allowed_raises(self, rdb):
        with pytest.raises(ErrorBase) as exc:
            Q.user_hardware_allowed(_payload(user_id="u-kind"), kind="banana")
        assert exc.value.error["error"] == "bad_request"

    def test_domain_not_found_raises(self, rdb):
        # domain_id set but the row (its create_dict) resolves empty -> not_found.
        rdb.get.return_value.__getitem__.return_value.run.return_value = None
        with pytest.raises(ErrorBase) as exc:
            Q.user_hardware_allowed(
                _payload(user_id="u-dom"), kind="quota", domain_id="missing"
            )
        assert exc.value.error["error"] == "not_found"
        assert exc.value.error["description_code"] == "not_found"

    def test_admin_branch_exposes_virtualization_nested(self, rdb):
        # kind="quota" skips every Alloweds lookup; admin/manager get the
        # virtualization_nested key, other roles do not.
        result = Q.user_hardware_allowed(
            _payload(role_id="admin", user_id="u-admin"), kind="quota"
        )
        assert result["virtualization_nested"] is False
        assert result["quota"] == {"vcpus": 4}

    def test_non_admin_has_no_virtualization_nested(self, rdb):
        result = Q.user_hardware_allowed(
            _payload(role_id="advanced", user_id="u-advanced"), kind="quota"
        )
        assert "virtualization_nested" not in result
