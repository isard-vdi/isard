# SPDX-License-Identifier: AGPL-3.0-or-later

"""Converting a template into a desktop makes its disk row writable."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from isardvdi_common.lib.domains.desktops import desktops as mod

DP = mod.DesktopsProcessed


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def converted(monkeypatch):
    disk = SimpleNamespace(
        id="disk-1",
        children=[],
        directory_path_as_usage=lambda usage: f"/isard/{usage}s",
        rsync=MagicMock(name="rsync"),
    )
    template = SimpleNamespace(
        id="tpl-1",
        user="owner",
        description="",
        storages=[disk],
        create_dict={"hardware": {"disks": [{"storage_id": "disk-1"}]}},
        xml="<domain/>",
        parents=[],
    )
    monkeypatch.setattr(
        mod, "TemplateToDesktop", lambda **d: SimpleNamespace(model_dump=lambda: d)
    )

    class FakeDomain:
        @staticmethod
        def exists(tid):
            return True

        def __new__(cls, tid):
            return template

    monkeypatch.setattr(mod, "Domain", FakeDomain)
    monkeypatch.setattr(
        mod.Helpers,
        "check_user_duplicated_domain_name",
        classmethod(lambda cls, *a, **k: None),
    )
    monkeypatch.setattr(
        mod.TemplatesProcessed, "is_duplicate", classmethod(lambda cls, tid: False)
    )
    monkeypatch.setattr(
        mod.RecycleBinHelpers,
        "get_template_dependant_recycle_bin_entries",
        classmethod(lambda cls, ids, field: []),
    )
    monkeypatch.setattr(
        DP, "new_from_template", classmethod(lambda cls, *a, **k: {"name": "d"})
    )
    monkeypatch.setattr(DP, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(DP), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    monkeypatch.setattr(mod.r, "table", lambda name: MagicMock(name=f"r.table({name})"))
    perms_writes = []
    monkeypatch.setattr(
        mod.Storage,
        "update_document",
        classmethod(lambda cls, sid, data, **k: perms_writes.append((sid, data))),
    )
    DP.convert_template_to_desktop({"template_id": "tpl-1", "name": "d"})
    return SimpleNamespace(disk=disk, perms_writes=perms_writes)


def test_the_disk_row_becomes_writable(converted):
    """The row was created read-only as a template's disk and nothing rewrote
    the marker when the domain became a desktop, so «only desktops» never moved
    it and the storage panel called it a template for ever."""
    assert converted.perms_writes == [("disk-1", {"perms": ["r", "w"]})]


def test_the_file_still_moves_to_the_desktops_directory(converted):
    converted.disk.rsync.assert_called_once()
    assert converted.disk.rsync.call_args.args[1] == "/isard/desktops"
