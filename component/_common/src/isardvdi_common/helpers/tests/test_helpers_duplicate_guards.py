# SPDX-License-Identifier: AGPL-3.0-or-later

"""Duplicate-name guards of ``Helpers`` in ``helpers.py``.

* ``check_duplicate`` -- raises ``conflict``/``duplicated_name`` when a row with
  the name already exists, and is silent otherwise.
* ``check_duplicates`` -- same, but bulk; ``raise_error=False`` returns the
  clashing rows instead of raising.

Only the rethink layer is stubbed; the decision is the code's.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_base import ErrorBase


@pytest.fixture
def stub(monkeypatch):
    from isardvdi_common.helpers import helpers as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.Helpers, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(mod.Helpers),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", table)
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", tuple(x)))
    return {"mod": mod, "Cls": mod.Helpers, "table": table}


def _rows(stub, rows):
    # get_all(...).filter(...).run()
    stub[
        "table"
    ].return_value.get_all.return_value.filter.return_value.run.return_value = rows


class TestCheckDuplicate:
    def test_existing_name_conflicts(self, stub):
        _rows(stub, [{"id": "x", "name": "dup"}])
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].check_duplicate("domains", "dup")
        assert exc.value.error["error"] == "conflict"
        assert exc.value.error["description_code"] == "duplicated_name"

    def test_free_name_is_silent(self, stub):
        _rows(stub, [])
        assert stub["Cls"].check_duplicate("domains", "free") is None


class TestCheckDuplicates:
    def test_clash_raises_by_default(self, stub):
        _rows(stub, [{"id": "x", "name": "dup"}])
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].check_duplicates("domains", ["dup"], user=None)
        assert exc.value.error["description_code"] == "duplicated_name"

    def test_clash_returned_when_not_raising(self, stub):
        rows = [{"id": "x", "name": "dup"}]
        _rows(stub, rows)
        got = stub["Cls"].check_duplicates(
            "domains", ["dup"], user=None, raise_error=False
        )
        assert got == rows

    def test_no_clash_returns_empty(self, stub):
        _rows(stub, [])
        assert stub["Cls"].check_duplicates("domains", ["free"], user=None) == []
