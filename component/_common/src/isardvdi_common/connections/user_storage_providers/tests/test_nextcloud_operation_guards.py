#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Decisions in ``NextcloudApi`` user operations from the OCS statuscode.

Each operation reads the provider's OCS ``statuscode`` and turns it into a
typed result or ``Error``. What matters (and is pinned) is the mapping:
"already exists" vs "not found" vs "bad data" vs a generic failure, plus
the admin-user refusals. The request plumbing is not exercised — only the
collaborator ``_request`` return value is stubbed, so each mapping decision
is the real code.
"""

import json

import pytest
from isardvdi_common.connections.user_storage_providers import nextcloud as mod
from isardvdi_common.helpers.error_factory import Error

NextcloudApi = mod.NextcloudApi


def _api():
    api = NextcloudApi("nc.example", verify_cert=False)
    api.set_basic_auth("admin", "pw")
    return api


def _reply(api, statuscode, data=None, message="m"):
    """Make ``api._request`` return an OCS envelope with this statuscode."""
    payload = {"ocs": {"meta": {"statuscode": statuscode, "message": message}}}
    if data is not None:
        payload["ocs"]["data"] = data
    api._request = lambda *a, **k: json.dumps(payload)
    return api


class TestGetUserGuards:
    def test_admin_user_rejected(self):
        with pytest.raises(Error) as exc:
            _api().get_user("admin")  # == self.user
        assert exc.value.error["error"] == "bad_request"

    def test_unknown_user_not_found(self):
        api = _reply(_api(), statuscode=998)
        with pytest.raises(Error) as exc:
            api.get_user("bob")
        assert exc.value.error["error"] == "not_found"

    def test_known_user_returns_data(self):
        api = _reply(_api(), statuscode=100, data={"id": "bob"})
        assert api.get_user("bob") == {"id": "bob"}


class TestGetUserQuotaGuards:
    def test_admin_user_rejected(self):
        with pytest.raises(Error) as exc:
            _api().get_user_quota("admin")
        assert exc.value.error["error"] == "bad_request"

    def test_unknown_user_not_found(self):
        api = _reply(_api(), statuscode=997, data={})
        with pytest.raises(Error) as exc:
            api.get_user_quota("bob")
        assert exc.value.error["error"] == "not_found"


class TestAddUserStatuscodeMapping:
    def test_already_exists_is_conflict(self):
        api = _reply(_api(), statuscode=102)
        with pytest.raises(Error) as exc:
            api.add_user("bob", "pw", 1024)
        assert exc.value.error["error"] == "conflict"

    def test_unknown_group_is_not_found(self):
        api = _reply(_api(), statuscode=104)
        with pytest.raises(Error) as exc:
            api.add_user("bob", "pw", 1024)
        assert exc.value.error["error"] == "not_found"

    def test_weak_password_is_bad_request(self):
        api = _reply(_api(), statuscode=107)
        with pytest.raises(Error) as exc:
            api.add_user("bob", "pw", 1024)
        assert exc.value.error["error"] == "bad_request"

    def test_unmapped_statuscode_is_internal_server(self):
        api = _reply(_api(), statuscode=103)
        with pytest.raises(Error) as exc:
            api.add_user("bob", "pw", 1024)
        assert exc.value.error["error"] == "internal_server"

    def test_success_returns_true(self):
        api = _reply(_api(), statuscode=100)
        assert api.add_user("bob", "pw", 1024) is True


class TestRemoveUserGuards:
    def test_admin_user_is_noop(self):
        # Removing the admin must be refused silently (return), never sent.
        api = _api()
        sent = []
        api._request = lambda *a, **k: sent.append(a) or "{}"
        assert api.remove_user("admin") is None
        assert sent == []

    def test_inexisting_user_is_not_found(self):
        api = _reply(_api(), statuscode=101)
        with pytest.raises(Error) as exc:
            api.remove_user("bob")
        assert exc.value.error["error"] == "not_found"

    def test_unmapped_statuscode_is_internal_server(self):
        api = _reply(_api(), statuscode=103)
        with pytest.raises(Error) as exc:
            api.remove_user("bob")
        assert exc.value.error["error"] == "internal_server"
