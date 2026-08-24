# SPDX-License-Identifier: AGPL-3.0-or-later

"""Access-control + quota guards of storage services (services/storage.py).

* ``get_storage`` -- the gate every storage op goes through: unknown storage ->
  not_found; missing user_id -> not_found; a non-admin/non-manager who is not the
  owner -> forbidden; owner / admin / same-category manager pass.
* ``StorageService.create_storage`` -- a requested size over the user's
  ``desktops_disk_size`` quota -> bad_request.

The real functions decide; only the models / quota helper are stubbed. Asserts
the ``Error`` type.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from api.services.error import Error
from api.services.storage import StorageService, get_storage


def _payload(role="user", user_id="me", category_id="cat-a"):
    return {"role_id": role, "user_id": user_id, "category_id": category_id}


class TestGetStorage:
    def test_unknown_storage_not_found(self):
        with patch("api.services.storage.Storage") as S:
            S.exists.return_value = False
            with pytest.raises(Error) as exc:
                get_storage(_payload(), "ghost")
        assert exc.value.error["error"] == "not_found"

    def test_missing_user_id_not_found(self):
        with patch("api.services.storage.Storage") as S:
            S.exists.return_value = True
            S.return_value = SimpleNamespace(user_id=None)
            with pytest.raises(Error) as exc:
                get_storage(_payload(), "s1")
        assert exc.value.error["error"] == "not_found"

    def test_non_owner_forbidden(self):
        with patch("api.services.storage.Storage") as S:
            S.exists.return_value = True
            S.return_value = SimpleNamespace(user_id="owner")
            with pytest.raises(Error) as exc:
                get_storage(_payload(role="user", user_id="intruder"), "s1")
        assert exc.value.error["error"] == "forbidden"

    def test_owner_passes(self):
        inst = SimpleNamespace(user_id="me")
        with patch("api.services.storage.Storage") as S:
            S.exists.return_value = True
            S.return_value = inst
            assert get_storage(_payload(user_id="me"), "s1") is inst

    def test_admin_passes(self):
        inst = SimpleNamespace(user_id="someone")
        with patch("api.services.storage.Storage") as S:
            S.exists.return_value = True
            S.return_value = inst
            assert get_storage(_payload(role="admin", user_id="admin-u"), "s1") is inst

    def test_manager_same_category_passes(self):
        inst = SimpleNamespace(user_id="owner")
        with (
            patch("api.services.storage.Storage") as S,
            patch("api.services.storage.RethinkUser") as U,
        ):
            S.exists.return_value = True
            S.return_value = inst
            U.get.return_value = {"category": "cat-a"}
            assert (
                get_storage(
                    _payload(role="manager", user_id="mgr", category_id="cat-a"), "s1"
                )
                is inst
            )

    def test_manager_other_category_forbidden(self):
        inst = SimpleNamespace(user_id="owner")
        with (
            patch("api.services.storage.Storage") as S,
            patch("api.services.storage.RethinkUser") as U,
        ):
            S.exists.return_value = True
            S.return_value = inst
            U.get.return_value = {"category": "cat-other"}
            with pytest.raises(Error) as exc:
                get_storage(
                    _payload(role="manager", user_id="mgr", category_id="cat-a"), "s1"
                )
        assert exc.value.error["error"] == "forbidden"


class TestCreateStorageQuota:
    def test_size_over_quota_rejected(self):
        with (
            patch("api.services.storage.check_task_priority", return_value="low"),
            patch("api.services.storage.Quotas") as Q,
        ):
            Q.get_applied_quota.return_value = {"quota": {"desktops_disk_size": 5}}
            with pytest.raises(Error) as exc:
                StorageService.create_storage(
                    _payload(), "desktop", "qcow2", None, "10G", "me", "low"
                )
        assert exc.value.error["error"] == "bad_request"
