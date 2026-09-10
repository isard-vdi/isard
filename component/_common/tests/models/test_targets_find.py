#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Targets.find_domain_target`` / ``get_domain_target``.

``get_domain_target`` passed ``traceback.format_exc()`` as the ``debug``
argument OUTSIDE any ``except`` block, so it evaluated to the literal
string ``"NoneType: None\\n"`` — truthy, which flips ``ErrorBase`` into
debug mode and fires six ``inspect.stack()`` walks on every 404. Callers
that just want to know whether a target exists (recycle-bin add paths)
should use a non-raising ``find_domain_target`` instead.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def targets_mod(monkeypatch):
    from isardvdi_common.models import targets as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.Targets, "_rdb_context", classmethod(lambda cls: _Ctx()))
    return mod


def _rows(monkeypatch, mod, rows):
    table = MagicMock(name="table-targets")
    table.get_all.return_value.run.return_value = rows
    monkeypatch.setattr(mod.r, "table", lambda name: table)


class TestFindDomainTarget:
    def test_returns_none_when_absent(self, targets_mod, monkeypatch):
        _rows(monkeypatch, targets_mod, [])
        assert targets_mod.Targets.find_domain_target("d1") is None

    def test_returns_row_when_present(self, targets_mod, monkeypatch):
        _rows(monkeypatch, targets_mod, [{"desktop_id": "d1", "ssh": {}}])
        assert targets_mod.Targets.find_domain_target("d1") == {
            "desktop_id": "d1",
            "ssh": {},
        }


class TestGetDomainTargetNotFound:
    def test_raises_target_not_found_without_stray_debug(
        self, targets_mod, monkeypatch
    ):
        _rows(monkeypatch, targets_mod, [])
        with pytest.raises(targets_mod.Error) as exc:
            targets_mod.Targets.get_domain_target("ghost")
        assert exc.value.status_code == 404
        assert exc.value.error["description_code"] == "target_not_found"
        # The stray traceback.format_exc() string must be gone.
        assert "NoneType: None" not in str(exc.value.error.get("debug", ""))

    def test_returns_row_when_present(self, targets_mod, monkeypatch):
        _rows(monkeypatch, targets_mod, [{"desktop_id": "d1", "ssh": {"x": 1}}])
        assert targets_mod.Targets.get_domain_target("d1") == {
            "desktop_id": "d1",
            "ssh": {"x": 1},
        }
