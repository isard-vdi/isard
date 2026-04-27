# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_users.py``.

Covers user CRUD, CSV operations, secondary groups, password reset,
group/category CRUD, quotas/limits, delete-checks, secrets, search,
broadcast, migration, group-category check, bastion-domain, and the
user-schema response.
"""

import pytest
from api.schemas.admin_users import (
    AdminBastionDomainData,
    AdminBroadcastData,
    AdminBulkUserCreateData,
    AdminCategoryAuthenticationData,
    AdminCategoryCreateData,
    AdminCategoryUpdateData,
    AdminCheckGroupCategoryData,
    AdminCheckMigratedData,
    AdminCSVUserEditData,
    AdminDeleteChecksData,
    AdminGroupCreateData,
    AdminGroupEnrollmentData,
    AdminGroupUpdateData,
    AdminLimitsUpdateData,
    AdminPasswordResetData,
    AdminQuotaUpdateData,
    AdminSecondaryGroupsData,
    AdminSecretCreateData,
    AdminUserCreateData,
    AdminUserDeleteData,
    AdminUserSchemaResponse,
    AdminUserSearchData,
    AdminUserUpdateData,
)
from pydantic import ValidationError

# ══════════════════════════════════════════════════════════════════════════
#  User CRUD
# ══════════════════════════════════════════════════════════════════════════


class TestAdminUserCreateData:
    _required = {
        "username": "u-new",
        "name": "New User",
        "category": "default",
        "group": "default-default",
        "role": "user",
        "password": "p4ssw0rd",
    }

    def test_accepts_required(self):
        u = AdminUserCreateData(**self._required)
        assert u.username == "u-new"
        # Defaults
        assert u.provider == "local"
        assert u.email == ""
        assert u.photo == ""
        assert u.bulk is False
        assert u.uid is None
        # default_factory: each instance gets its own list.
        a = AdminUserCreateData(**self._required)
        b = AdminUserCreateData(**self._required)
        assert a.secondary_groups is not b.secondary_groups
        assert a.secondary_groups == []

    @pytest.mark.parametrize(
        "missing", ["username", "name", "category", "group", "role", "password"]
    )
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            AdminUserCreateData(**payload)

    def test_secondary_groups_list(self):
        u = AdminUserCreateData(**self._required, secondary_groups=["g1", "g2"])
        assert u.secondary_groups == ["g1", "g2"]


class TestAdminUserUpdateData:
    """All fields Optional — partial updates."""

    def test_accepts_empty(self):
        u = AdminUserUpdateData()
        assert u.ids is None
        assert u.bulk is False  # bulk has default False (not None)

    def test_quota_accepts_bool_or_dict(self):
        """quota: Optional[Union[bool, dict]] — False = unlimited,
        dict = explicit quota. Pin both."""
        assert AdminUserUpdateData(quota=False).quota is False
        assert AdminUserUpdateData(quota={"hard": 100}).quota == {"hard": 100}

    def test_partial_update(self):
        u = AdminUserUpdateData(name="renamed")
        dump = u.model_dump(exclude_none=True)
        # bulk=False survives exclude_none (it's not None)
        assert dump == {"name": "renamed", "bulk": False}


class TestAdminUserDeleteData:
    def test_user_required(self):
        with pytest.raises(ValidationError):
            AdminUserDeleteData()

    def test_default_delete_user_true(self):
        """delete_user defaults True — the route relies on it for the
        no-body case."""
        d = AdminUserDeleteData(user=["u-1"])
        assert d.delete_user is True

    def test_explicit_false(self):
        d = AdminUserDeleteData(user=["u-1"], delete_user=False)
        assert d.delete_user is False


class TestAdminBulkUserCreateData:
    def test_users_required(self):
        with pytest.raises(ValidationError):
            AdminBulkUserCreateData()

    def test_accepts_arbitrary_dicts(self):
        u = AdminBulkUserCreateData(
            users=[{"username": "u1"}, {"username": "u2", "extra": "x"}]
        )
        assert len(u.users) == 2


# ══════════════════════════════════════════════════════════════════════════
#  CSV
# ══════════════════════════════════════════════════════════════════════════


class TestAdminCSVUserEditData:
    def test_users_required(self):
        with pytest.raises(ValidationError):
            AdminCSVUserEditData()


# ══════════════════════════════════════════════════════════════════════════
#  Secondary groups + password
# ══════════════════════════════════════════════════════════════════════════


class TestAdminSecondaryGroupsData:
    @pytest.mark.parametrize("missing", ["ids", "secondary_groups"])
    def test_both_required(self, missing):
        payload = {"ids": ["u-1"], "secondary_groups": ["g-1"]}
        del payload[missing]
        with pytest.raises(ValidationError):
            AdminSecondaryGroupsData(**payload)


class TestAdminPasswordResetData:
    @pytest.mark.parametrize("missing", ["user_id", "password"])
    def test_both_required(self, missing):
        payload = {"user_id": "u-1", "password": "p"}
        del payload[missing]
        with pytest.raises(ValidationError):
            AdminPasswordResetData(**payload)


# ══════════════════════════════════════════════════════════════════════════
#  Groups
# ══════════════════════════════════════════════════════════════════════════


class TestAdminGroupCreateData:
    def test_name_required(self):
        with pytest.raises(ValidationError):
            AdminGroupCreateData()

    def test_defaults(self):
        g = AdminGroupCreateData(name="g")
        assert g.description == ""
        assert g.parent_category is None


class TestAdminGroupUpdateData:
    @pytest.mark.parametrize("missing", ["id", "name"])
    def test_id_and_name_required(self, missing):
        payload = {"id": "g-1", "name": "g"}
        del payload[missing]
        with pytest.raises(ValidationError):
            AdminGroupUpdateData(**payload)


class TestAdminGroupEnrollmentData:
    @pytest.mark.parametrize("missing", ["id", "action"])
    def test_id_and_action_required(self, missing):
        payload = {"id": "g-1", "action": "enable"}
        del payload[missing]
        with pytest.raises(ValidationError):
            AdminGroupEnrollmentData(**payload)


# ══════════════════════════════════════════════════════════════════════════
#  Categories
# ══════════════════════════════════════════════════════════════════════════


class TestAdminCategoryCreateData:
    def test_name_required(self):
        with pytest.raises(ValidationError):
            AdminCategoryCreateData()

    def test_defaults(self):
        c = AdminCategoryCreateData(name="c")
        assert c.description == ""
        assert c.frontend is True
        assert c.custom_url_name == ""


class TestAdminCategoryUpdateData:
    @pytest.mark.parametrize("missing", ["id", "name"])
    def test_id_and_name_required(self, missing):
        payload = {"id": "c-1", "name": "c"}
        del payload[missing]
        with pytest.raises(ValidationError):
            AdminCategoryUpdateData(**payload)


class TestAdminCategoryAuthenticationData:
    def test_authentication_required(self):
        with pytest.raises(ValidationError):
            AdminCategoryAuthenticationData()

    def test_accepts_dict(self):
        d = AdminCategoryAuthenticationData(authentication={"local": {}})
        assert d.authentication == {"local": {}}


# ══════════════════════════════════════════════════════════════════════════
#  Quotas, limits
# ══════════════════════════════════════════════════════════════════════════


class TestAdminQuotaUpdateData:
    def test_quota_required(self):
        with pytest.raises(ValidationError):
            AdminQuotaUpdateData()

    def test_quota_bool_or_dict(self):
        assert AdminQuotaUpdateData(quota=False).quota is False
        assert AdminQuotaUpdateData(quota={"hard": 1}).quota == {"hard": 1}

    def test_defaults(self):
        d = AdminQuotaUpdateData(quota=False)
        assert d.propagate is False
        assert d.role == "all_roles"


class TestAdminLimitsUpdateData:
    def test_limits_required(self):
        with pytest.raises(ValidationError):
            AdminLimitsUpdateData()

    def test_limits_bool_or_dict(self):
        assert AdminLimitsUpdateData(limits=True).limits is True
        assert AdminLimitsUpdateData(limits={"max": 10}).limits == {"max": 10}


# ══════════════════════════════════════════════════════════════════════════
#  Misc
# ══════════════════════════════════════════════════════════════════════════


class TestAdminDeleteChecksData:
    def test_ids_required(self):
        with pytest.raises(ValidationError):
            AdminDeleteChecksData()


class TestAdminSecretCreateData:
    @pytest.mark.parametrize("missing", ["category_id", "secret"])
    def test_required(self, missing):
        payload = {"category_id": "default", "secret": "s"}
        del payload[missing]
        with pytest.raises(ValidationError):
            AdminSecretCreateData(**payload)

    def test_description_default_empty(self):
        d = AdminSecretCreateData(category_id="default", secret="s")
        assert d.description == ""


class TestAdminUserSearchData:
    def test_term_required(self):
        with pytest.raises(ValidationError):
            AdminUserSearchData()


class TestAdminBroadcastData:
    @pytest.mark.parametrize("missing", ["type", "message"])
    def test_required(self, missing):
        payload = {"type": "info", "message": "m"}
        del payload[missing]
        with pytest.raises(ValidationError):
            AdminBroadcastData(**payload)


class TestAdminCheckMigratedData:
    def test_users_required(self):
        with pytest.raises(ValidationError):
            AdminCheckMigratedData()


class TestAdminCheckGroupCategoryData:
    def test_all_optional(self):
        """Both fields optional — empty body means "no check"."""
        d = AdminCheckGroupCategoryData()
        assert d.category is None
        assert d.group is None


class TestAdminBastionDomainData:
    def test_bastion_domain_required(self):
        with pytest.raises(ValidationError):
            AdminBastionDomainData()

    def test_accepts_str_bool_none(self):
        """bastion_domain: Union[str, bool, None] — string sets the
        domain, bool toggles, None clears. Pin all three."""
        assert (
            AdminBastionDomainData(bastion_domain="b.example.com").bastion_domain
            == "b.example.com"
        )
        assert AdminBastionDomainData(bastion_domain=False).bastion_domain is False
        assert AdminBastionDomainData(bastion_domain=None).bastion_domain is None


class TestAdminUserSchemaResponse:
    def test_role_required(self):
        with pytest.raises(ValidationError):
            AdminUserSchemaResponse()

    def test_minimal(self):
        r = AdminUserSchemaResponse(role=["admin", "user"])
        assert r.role == ["admin", "user"]
        assert r.category is None

    def test_full(self):
        r = AdminUserSchemaResponse(
            role=["admin"],
            category=[{"id": "default"}],
            group=[{"id": "g-1"}],
        )
        assert r.category[0]["id"] == "default"
