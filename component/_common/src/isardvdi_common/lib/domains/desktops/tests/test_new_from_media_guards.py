#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Precondition guards on ``DesktopsProcessed.new_from_media``.

A desktop built from an installer medium (ISO/disk) pins several rows by
id — the virt-install XML, the medium, the graphics/videos/interfaces
hardware — and rejects the create if any of them is missing or if the
requested hardware exceeds the user's quota. Each of these gates raises a
typed ``Error`` *before* the ``domains`` insert; a gate that stops firing
would let a user create a desktop referencing non-existent hardware.

The rethink layer is stubbed (per-table ``r.table`` mocks whose terminal
``.run`` returns the row the guard inspects) but ``new_from_media`` itself
runs unmocked, so every reject decision is taken by production code.

Guards pinned (line numbers on ``origin/main``):
* virt-install xml missing        (L1495) -> not_found
* media missing                   (L1504) -> not_found
* no graphics resolved            (L1519) -> not_found
* no videos resolved              (L1534) -> not_found
* interfaces count mismatch       (L1549) -> not_found
* hardware limited by quota       (L1669) -> bad_request
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktops as mod

DP = mod.DesktopsProcessed


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _payload():
    return {"user_id": "u-1", "category_id": "cat-1", "group_id": "grp-1"}


def _data():
    return {
        "id": "d-1",
        "name": "media-desktop",
        "description": "from media",
        "kind": "iso",
        "forced_hyp": False,
        "favourite_hyp": False,
        "xml_id": "xml-1",
        "media_id": "media-1",
        "hardware": {
            "graphics": ["default"],
            "videos": ["default"],
            "interfaces": ["default"],
            "boot_order": ["disk"],
            "disk_bus": "virtio",
            "memory": 2,
            "vcpus": 2,
            "reservables": {"vgpus": None},
            # no disk_size -> disks=[] (ISO-only), so no Storage.new_dict
        },
    }


@pytest.fixture
def stub(monkeypatch):
    """Stub the rethink layer + non-DB collaborators; happy-path defaults.

    ``tbl`` maps a table name to the ``r.table(name)`` MagicMock so a test
    can rewrite exactly the ``.run`` result the guard it targets reads.
    Defaults let every guard pass, so a test only has to break one thing.
    """
    monkeypatch.setattr(DP, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(DP), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )

    tbl = {
        name: MagicMock(name=f"r.table({name})")
        for name in (
            "users",
            "virt_install",
            "media",
            "graphics",
            "videos",
            "interfaces",
            "domains",
        )
    }
    monkeypatch.setattr(mod.r, "table", lambda name: tbl[name])
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", x))

    # username: users.get(uid).pluck("username")["username"].run(conn)
    tbl[
        "users"
    ].get.return_value.pluck.return_value.__getitem__.return_value.run.return_value = (
        "bob"
    )
    # single-row .get(...).run(...) lookups
    tbl["virt_install"].get.return_value.run.return_value = {"id": "xml-1"}
    tbl["media"].get.return_value.run.return_value = {"id": "media-1"}
    # get_all(...).run(...) list lookups (iterated for their "id")
    tbl["graphics"].get_all.return_value.run.return_value = [{"id": "default"}]
    tbl["videos"].get_all.return_value.run.return_value = [{"id": "default"}]
    tbl["interfaces"].get_all.return_value.run.return_value = [{"id": "default"}]

    monkeypatch.setattr(
        mod.Helpers, "gen_new_mac", classmethod(lambda cls: "52:54:00:00:00:01")
    )
    monkeypatch.setattr(
        mod.Cards, "get_domain_stock_card", classmethod(lambda cls, did: "")
    )
    monkeypatch.setattr(
        mod.Quotas,
        "limit_user_hardware_allowed",
        classmethod(lambda cls, payload, cd: {**cd, "limited_hardware": []}),
    )
    return tbl


class TestNewFromMediaGuards:
    def test_xml_not_found(self, stub):
        stub["virt_install"].get.return_value.run.return_value = None
        with pytest.raises(Error) as exc:
            DP.new_from_media(_payload(), _data())
        assert exc.value.error["error"] == "not_found"
        assert exc.value.error["description_code"] == "not_found"

    def test_media_not_found(self, stub):
        stub["media"].get.return_value.run.return_value = None
        with pytest.raises(Error) as exc:
            DP.new_from_media(_payload(), _data())
        assert exc.value.error["error"] == "not_found"
        assert exc.value.error["description_code"] == "not_found"

    def test_no_graphics(self, stub):
        stub["graphics"].get_all.return_value.run.return_value = []
        with pytest.raises(Error) as exc:
            DP.new_from_media(_payload(), _data())
        assert exc.value.error["error"] == "not_found"
        assert exc.value.error["description_code"] == "not_found"

    def test_no_videos(self, stub):
        stub["videos"].get_all.return_value.run.return_value = []
        with pytest.raises(Error) as exc:
            DP.new_from_media(_payload(), _data())
        assert exc.value.error["error"] == "not_found"
        assert exc.value.error["description_code"] == "not_found"

    def test_interfaces_mismatch(self, stub):
        # Request one interface but the DB resolves none: count mismatch.
        stub["interfaces"].get_all.return_value.run.return_value = []
        with pytest.raises(Error) as exc:
            DP.new_from_media(_payload(), _data())
        assert exc.value.error["error"] == "not_found"
        assert exc.value.error["description_code"] == "not_found"

    def test_limited_hardware(self, stub, monkeypatch):
        # All rows resolve; the quota limiter flags disallowed hardware, so
        # the create is rejected before the domains insert.
        monkeypatch.setattr(
            mod.Quotas,
            "limit_user_hardware_allowed",
            classmethod(lambda cls, payload, cd: {**cd, "limited_hardware": ["vcpus"]}),
        )
        with pytest.raises(Error) as exc:
            DP.new_from_media(_payload(), _data())
        assert exc.value.error["error"] == "bad_request"
