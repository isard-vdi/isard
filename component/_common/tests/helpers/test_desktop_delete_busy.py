# SPDX-License-Identifier: AGPL-3.0-or-later

"""``DesktopEvents.desktop_delete`` refuses a desktop the engine is still acting on.

Binning a row mid-create or mid-start loses the engine's in-memory action, and the
restored desktop then waits for it forever. Only rethink and the recycle bin are
stubbed; the status decision is the code's.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_base import ErrorBase


@pytest.fixture
def stub(monkeypatch):
    from isardvdi_common.helpers import desktop_events as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.DesktopEvents, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.DesktopEvents),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", table)
    rcb = MagicMock(name="RecycleBinDesktop")
    monkeypatch.setattr(mod, "RecycleBinDesktop", rcb)
    rcb.return_value.owner_id = "u1"
    monkeypatch.setattr(
        mod.RecycleBinHelpers,
        "get_user_recycle_bin_cutoff_time",
        staticmethod(lambda owner: 24),
    )

    def row(status):
        table.return_value.get.return_value.pluck.return_value.default.return_value.run.return_value = {
            "tag": False,
            "status": status,
        }

    return {"Cls": mod.DesktopEvents, "row": row, "rcb": rcb}


@pytest.mark.parametrize(
    "status", ["CreatingDisk", "CreatingDomain", "Starting", "Updating"]
)
def test_a_busy_desktop_is_not_binned(stub, status):
    stub["row"](status)
    with pytest.raises(ErrorBase) as exc:
        stub["Cls"].desktop_delete("d1", "u1")
    assert exc.value.error["description_code"] == "desktop_busy"
    assert exc.value.status_code == 428
    stub["rcb"].assert_not_called()


@pytest.mark.parametrize("status", ["Stopped", "Failed", "Started"])
def test_a_desktop_at_rest_is_binned(stub, status):
    stub["row"](status)
    stub["Cls"].desktop_delete("d1", "u1")
    stub["rcb"].return_value.add.assert_called_once_with("d1")
