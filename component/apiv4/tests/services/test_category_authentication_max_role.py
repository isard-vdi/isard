# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-provider ``max_role`` on category authentication: value validation and
the admin-only guard on setting/changing it.

``max_role`` (user|advanced|manager|admin, or absent) caps the role a provider
can grant. Its *value* is validated like the rest of the auth payload, and only
an admin may set or change it — a manager with the authentication permission
keeps the stored value (omitted is backfilled; a different value is 403),
mirroring how secrets are preserved.
"""

import pytest
from api.services.admin.categories import (
    _enforce_max_role_admin_only,
    _validate_category_authentication,
)
from api.services.error import Error


def _auth(max_role):
    return {"local": {"disabled": True, "max_role": max_role}}


class TestValidateMaxRoleValue:
    @pytest.mark.parametrize("role", ["user", "advanced", "manager", "admin"])
    def test_accepts_valid_roles(self, role):
        _validate_category_authentication(_auth(role))  # no raise

    def test_absent_and_empty_pass(self):
        _validate_category_authentication({"local": {"disabled": True}})
        _validate_category_authentication(_auth(""))

    def test_rejects_unknown_role(self):
        with pytest.raises(Error) as exc:
            _validate_category_authentication(_auth("superadmin"))
        assert exc.value.status_code == 400
        assert exc.value.error["description_code"] == "authentication_invalid"


class TestMaxRoleAdminOnly:
    def test_admin_may_set_and_change(self):
        new = {"saml": {"max_role": "manager"}}
        _enforce_max_role_admin_only(new, {"saml": {"max_role": "advanced"}}, True)
        assert new["saml"]["max_role"] == "manager"  # untouched for admin

    def test_manager_omitting_backfills_stored(self):
        new = {"saml": {"disabled": False}}
        _enforce_max_role_admin_only(new, {"saml": {"max_role": "advanced"}}, False)
        assert new["saml"]["max_role"] == "advanced"

    def test_manager_keeping_same_value_allowed(self):
        new = {"saml": {"max_role": "advanced"}}
        _enforce_max_role_admin_only(new, {"saml": {"max_role": "advanced"}}, False)
        assert new["saml"]["max_role"] == "advanced"

    def test_manager_changing_is_forbidden(self):
        new = {"saml": {"max_role": "admin"}}
        with pytest.raises(Error) as exc:
            _enforce_max_role_admin_only(new, {"saml": {"max_role": "advanced"}}, False)
        assert exc.value.status_code == 403
        assert exc.value.error["description_code"] == "max_role_admin_only"

    @pytest.mark.parametrize("sent", ["", None])
    @pytest.mark.parametrize(
        "existing", [{"saml": {"disabled": False}}, {"saml": {"max_role": ""}}]
    )
    def test_manager_resaving_no_cap_allowed(self, sent, existing):
        # The old webapp sends max_role "" for every provider a manager re-saves.
        new = {"saml": {"disabled": False, "max_role": sent}}
        _enforce_max_role_admin_only(new, existing, False)  # no raise

    def test_manager_clearing_stored_cap_is_forbidden(self):
        new = {"saml": {"max_role": ""}}
        with pytest.raises(Error) as exc:
            _enforce_max_role_admin_only(new, {"saml": {"max_role": "advanced"}}, False)
        assert exc.value.status_code == 403

    def test_manager_setting_when_none_stored_is_forbidden(self):
        new = {"saml": {"max_role": "manager"}}
        with pytest.raises(Error) as exc:
            _enforce_max_role_admin_only(new, {"saml": {"disabled": False}}, False)
        assert exc.value.status_code == 403
