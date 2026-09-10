#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guard paths of ``api_admin.py``.

* ``_pluck_field_names`` -- flattens a nested pluck arg to its leaf field names.
* ``_validate_pluck_safe`` -- the pluck injection guard: denies pluck entirely on
  a ``"*"`` table (config), rejects any-table-sensitive fields (password/token),
  rejects per-table-sensitive fields (users.vpn) while allowing that same name
  on a table that doesn't blocklist it, and passes an ordinary pluck.
* ``_validate_table`` -- rejects a table not in the schema (``not_found``).

These are pure/near-pure validators; only ``system_tables`` (a process cache
over rethink) is stubbed. Errors assert type + ``description_code``.
"""

import pytest
from isardvdi_common.helpers.error_base import ErrorBase


class TestPluckFieldNames:
    def test_flattens_nested_dict_and_list(self):
        from isardvdi_common.lib.api_admin import _pluck_field_names

        got = set(_pluck_field_names({"left": ["name", "id"], "right": {"cat": ["x"]}}))
        assert got == {"left", "name", "id", "right", "cat", "x"}


class TestValidatePluckSafe:
    def _fn(self):
        from isardvdi_common.lib.api_admin import _validate_pluck_safe

        return _validate_pluck_safe

    # NOTE: a "pluck=None is allowed" case is intentionally NOT tested: the
    # allow outcome is protected by two guards (the ``pluck is None`` early
    # return and the later ``if not requested`` return), so no single mutation
    # flips it and the test could not be seen to fail.

    def test_star_table_denies_pluck_entirely(self):
        with pytest.raises(ErrorBase) as exc:
            self._fn()("config", ["anything"])
        assert exc.value.error["error"] == "forbidden"
        assert exc.value.error["description_code"] == "not_enough_rights"

    def test_any_table_sensitive_field_rejected(self):
        with pytest.raises(ErrorBase) as exc:
            self._fn()("domains", ["id", "password"])
        assert exc.value.error["description_code"] == "not_enough_rights"

    def test_per_table_sensitive_field_rejected(self):
        with pytest.raises(ErrorBase) as exc:
            self._fn()("users", ["vpn"])
        assert exc.value.error["error"] == "forbidden"

    def test_same_field_allowed_on_a_table_that_does_not_block_it(self):
        # ``vpn`` is sensitive on ``users`` but not on ``domains`` -> allowed.
        assert self._fn()("domains", ["vpn"]) is None

    def test_ordinary_pluck_passes(self):
        assert self._fn()("users", ["id", "name"]) is None


class TestValidateTable:
    def test_unknown_table_not_found(self, monkeypatch):
        from isardvdi_common.lib import api_admin as mod

        monkeypatch.setattr(
            mod.ApiAdmin, "system_tables", classmethod(lambda cls: ["users", "domains"])
        )
        with pytest.raises(ErrorBase) as exc:
            mod.ApiAdmin._validate_table("nope")
        assert exc.value.error["error"] == "not_found"

    def test_known_table_passes(self, monkeypatch):
        from isardvdi_common.lib import api_admin as mod

        monkeypatch.setattr(
            mod.ApiAdmin, "system_tables", classmethod(lambda cls: ["users", "domains"])
        )
        assert mod.ApiAdmin._validate_table("users") is None
