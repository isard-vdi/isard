# SPDX-License-Identifier: AGPL-3.0-or-later

"""Reading the shared-storage stall the engine declares."""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_base import ErrorBase


@pytest.fixture
def stall(monkeypatch):
    from isardvdi_common.helpers import shared_storage_stall as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.SharedStorageStall, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.SharedStorageStall),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
        raising=False,
    )
    table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", table)
    monkeypatch.setattr(mod.SharedStorageStall, "_cached_at", 0.0)
    monkeypatch.setattr(mod.SharedStorageStall, "_cached", None)
    run = table.return_value.get.return_value.pluck.return_value.run

    def stored(value):
        run.return_value = {"shared_storage_stall": value} if value else {}

    return mod.SharedStorageStall, stored, run


def test_inactive_when_never_declared(stall):
    cls, stored, _ = stall
    stored(None)
    assert cls.active() is False
    cls.raise_if_active()


def test_active_raises_503(stall):
    cls, stored, _ = stall
    stored({"active": True, "since": 1.0, "mounts": ["/isard/groups"]})
    with pytest.raises(ErrorBase) as exc:
        cls.raise_if_active()
    assert exc.value.status_code == 503
    assert exc.value.error["msg"] == "Service temporarily unavailable"
    assert exc.value.error["description_code"] == "service_temporarily_unavailable"


def test_a_cleared_condition_lets_starts_through(stall):
    cls, stored, _ = stall
    stored({"active": False, "since": 1.0, "cleared_at": 2.0})
    assert cls.active() is False


def test_reads_are_cached_briefly(stall):
    cls, stored, run = stall
    stored({"active": True})
    cls.active()
    cls.active()
    assert run.call_count == 1


def test_an_unreadable_condition_never_blocks_a_start(stall):
    cls, _, run = stall
    run.side_effect = RuntimeError("db down")
    assert cls.active() is False
    cls.raise_if_active()
