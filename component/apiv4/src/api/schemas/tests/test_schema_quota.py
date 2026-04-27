# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/quota.py``."""

import pytest
from api.schemas.quota import AdminQuotaResponse
from pydantic import ValidationError


class TestAdminQuotaResponse:
    """The Quotas common helper returns slightly different shapes per
    kind — the schema is intentionally loose. Pin the loose contract so
    a future tightening is intentional and updates the helper tests too.
    """

    def test_quota_required(self):
        with pytest.raises(ValidationError):
            AdminQuotaResponse()

    def test_quota_false_means_unlimited(self):
        """quota=False is the canonical "no quota configured" value —
        NOT a missing/null value."""
        r = AdminQuotaResponse(quota=False)
        assert r.quota is False
        assert r.limits is False  # default
        assert r.grouplimits is None  # default

    def test_quota_dict(self):
        r = AdminQuotaResponse(
            quota={"desktops": 10, "templates": 5, "vcpus": 8, "memory": 16384}
        )
        assert r.quota["desktops"] == 10

    def test_grouplimits_only_on_group_kind(self):
        """grouplimits is Optional and present only on group kind
        lookups — pin both shapes pass schema."""
        r_user = AdminQuotaResponse(quota={"desktops": 10}, limits={"desktops": 20})
        assert r_user.grouplimits is None
        r_group = AdminQuotaResponse(
            quota={"desktops": 10},
            limits={"desktops": 20},
            grouplimits={"desktops": 30},
        )
        assert r_group.grouplimits == {"desktops": 30}

    def test_extra_keys_allowed(self):
        """class Config: extra = 'allow' — future fields added to the
        Quotas helper land in the response without a schema migration.
        Pin so a refactor that flips to extra='ignore' is loud."""
        r = AdminQuotaResponse(quota={}, limits={}, grouplimits=None, future_field="x")
        # extra=allow keeps the unknown field on the model.
        assert r.model_dump()["future_field"] == "x"
