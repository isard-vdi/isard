#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A failed vGPU pool release logs the recycle-bin entry it was freeing."""

from unittest.mock import MagicMock

from isardvdi_common.helpers import recycle_bin as mod


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_failed_release_logs_the_entry_id(monkeypatch):
    entry = MagicMock(name="recycle_bin")
    entry.get.return_value.pluck.return_value.default.return_value.run.return_value = {
        "desktops": [{"id": "desk-1"}]
    }
    vgpus = MagicMock(name="vgpus")
    vgpus.pluck.return_value.run.side_effect = RuntimeError("boom")
    monkeypatch.setattr(
        mod.r, "table", lambda name: entry if name == "recycle_bin" else vgpus
    )
    monkeypatch.setattr(mod.Helpers, "_rdb_context", classmethod(lambda cls: _Ctx()))
    errors = MagicMock()
    monkeypatch.setattr(mod.log, "error", errors)

    mod.Helpers.free_vgpu_pool("rb-1")

    errors.assert_called_once()
    assert errors.call_args.args[1] == "rb-1"
