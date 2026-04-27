# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_roles.py``."""

import pytest
from api.schemas.admin_roles import RoleListResponse, RoleResponse
from pydantic import ValidationError


class TestRoleResponse:
    def test_id_required(self):
        with pytest.raises(ValidationError):
            RoleResponse()

    def test_minimal(self):
        r = RoleResponse(id="admin")
        assert r.id == "admin"
        assert r.name is None
        assert r.sortorder is None

    def test_full(self):
        r = RoleResponse(
            id="admin", name="Administrator", description="Full access", sortorder=1
        )
        assert r.sortorder == 1


class TestRoleListResponse:
    def test_roles_required(self):
        with pytest.raises(ValidationError):
            RoleListResponse()

    def test_accepts_empty(self):
        assert RoleListResponse(roles=[]).roles == []

    def test_accepts_arbitrary_dicts(self):
        """roles: List[Dict[str, Any]] — pin so a typed sub-model
        change is intentional."""
        r = RoleListResponse(roles=[{"id": "admin"}, {"id": "user", "name": "User"}])
        assert len(r.roles) == 2
