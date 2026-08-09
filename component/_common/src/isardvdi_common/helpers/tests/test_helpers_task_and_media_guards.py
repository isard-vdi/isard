#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Validation guards in ``Helpers``: task priority/retry and media extension.

* check_task_priority: an unknown tier is rejected (bad_request); a valid
  tier passes through unchanged.
* check_task_retry: a non-admin (or None) is normalized to 0; an admin's
  out-of-range or non-integer retry is rejected (bad_request); a valid
  admin retry passes.
* generate_db_media: an upload with an unrecognized extension is rejected
  (unknown_extension).

Only ``get_user_data`` is stubbed for the media case; everything else runs
unmocked.
"""

import pytest
from isardvdi_common.helpers import helpers as mod
from isardvdi_common.helpers.error_factory import Error

H = mod.Helpers


class TestCheckTaskPriority:
    def test_unknown_priority_rejected(self):
        with pytest.raises(Error) as exc:
            H.check_task_priority({"role_id": "admin"}, "turbo")
        assert exc.value.error["error"] == "bad_request"

    def test_valid_tier_passes(self):
        assert H.check_task_priority({"role_id": "user"}, "standard") == "standard"

    def test_legacy_value_passes(self):
        assert H.check_task_priority({"role_id": "user"}, "high") == "high"


class TestCheckTaskRetry:
    def test_non_admin_forced_to_zero(self):
        assert H.check_task_retry({"role_id": "user"}, 3) == 0

    def test_admin_out_of_range_rejected(self):
        with pytest.raises(Error) as exc:
            H.check_task_retry({"role_id": "admin"}, 9)
        assert exc.value.error["error"] == "bad_request"

    def test_admin_non_integer_rejected(self):
        with pytest.raises(Error) as exc:
            H.check_task_retry({"role_id": "admin"}, "abc")
        assert exc.value.error["error"] == "bad_request"

    def test_admin_valid_retry_passes(self):
        assert H.check_task_retry({"role_id": "admin"}, 3) == 3


class TestGenerateDbMediaExtension:
    def test_unknown_extension_rejected(self, monkeypatch):
        # get_user_data hits the DB before the extension check; stub it so the
        # extension guard is what we exercise.
        monkeypatch.setattr(
            H,
            "get_user_data",
            classmethod(
                lambda cls, user_id="admin": {
                    "category": "c",
                    "group": "g",
                    "user": "u",
                    "username": "admin",
                }
            ),
        )
        with pytest.raises(Error) as exc:
            H.generate_db_media("/path/to/file.txt", 1024)
        assert exc.value.error["description_code"] == "unknown_extension"
