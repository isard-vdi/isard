# SPDX-License-Identifier: AGPL-3.0-or-later

"""A template must never carry the source's MAC addresses.

``new_template`` copied ``create_dict.hardware`` whole and only replaced the
disks, so every template made from a desktop shipped that desktop's MACs;
``duplicate_template`` copies the whole document, so it did the same. Measured
on a production install: 5.373 of 24.958 interfaces held a duplicated address.

Both functions run for real here — only rethink, the storage/domain models and
the address generator are stubbed, so the assertions are on what the code
actually writes to the ``domains`` table.
"""

from unittest.mock import MagicMock

import pytest

SOURCE_MAC = "52:54:00:aa:bb:cc"
SECOND_MAC = "52:54:00:aa:bb:dd"


@pytest.fixture
def stub(monkeypatch):
    from isardvdi_common.lib.domains.templates import templates as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.TemplatesProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.TemplatesProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    tables = {}

    def router(name):
        return tables.setdefault(name, MagicMock(name=f"table-{name}"))

    monkeypatch.setattr(mod.r, "table", MagicMock(side_effect=router))

    counter = {"n": 0}

    def _mac():
        counter["n"] += 1
        return "52:54:00:00:00:%02x" % counter["n"]

    monkeypatch.setattr(mod.Helpers, "gen_new_mac", staticmethod(_mac))

    cards = MagicMock(name="Cards")
    cards.get_domain_stock_card.return_value = {
        "type": "stock",
        "id": "card-1",
        "url": "/assets/img/desktops/stock/card-1.jpg",
    }
    monkeypatch.setattr(mod, "Cards", cards)

    return {
        "mod": mod,
        "Cls": mod.TemplatesProcessed,
        "router": router,
        "mp": monkeypatch,
    }


def _source_desktop(interfaces):
    return {
        "id": "desktop-1",
        "status": "Stopped",
        "server": False,
        "xml": "",
        "icon": "",
        "os": "linux",
        "guest_properties": {"viewers": {}, "credentials": {}, "fullscreen": False},
        "favourite_hyp": False,
        "forced_hyp": False,
        "parents": [],
        "create_dict": {
            "hardware": {
                "boot_order": ["disk"],
                "disk_bus": "default",
                "disks": [
                    {
                        "extension": "qcow2",
                        "file": "/isard/groups/d1.qcow2",
                        "storage_id": "src-storage-id",
                    }
                ],
                "floppies": [],
                "graphics": ["default"],
                "interfaces": interfaces,
                "isos": [],
                "memory": 1024 * 1024,
                "qos_disk_id": False,
                "vcpus": 1,
                "videos": ["default"],
            },
            "origin": "media-1",
            "personal_vlans": False,
            "reservables": {"vgpus": None},
        },
    }


def _arm_new_template(stub, desktop):
    mod, mp = stub["mod"], stub["mp"]
    stub["router"]("users").get.return_value.pluck.return_value.run.return_value = {
        "id": "u1",
        "category": "c1",
        "group": "g1",
        "username": "n",
    }
    stub["router"]("domains").get.return_value.run.return_value = desktop

    domain = MagicMock(name="Domain")
    domain.return_value.storage_ready = True
    domain.exists.return_value = False
    mp.setattr(mod, "Domain", domain)

    storage = MagicMock(name="Storage")
    storage.exists.return_value = True
    storage.return_value.status = "ready"
    storage.return_value.parent = "parent-storage-id"
    storage.new_dict.return_value.id = "tpl-storage-id"
    storage.new_dict.return_value.path = "/isard/templates/tpl.qcow2"
    mp.setattr(mod, "Storage", storage)

    import isardvdi_common.lib.task_index as task_index

    mp.setattr(task_index, "current_task_id", lambda *a, **k: None)
    return stub["router"]("domains")


def _inserted_interfaces(domains_table):
    (inserted,), _ = domains_table.insert.call_args
    return inserted["create_dict"]["hardware"]["interfaces"]


class TestNewTemplate:
    def test_the_template_does_not_inherit_the_desktop_macs(self, stub):
        desktop = _source_desktop(
            [
                {"id": "default", "mac": SOURCE_MAC},
                {"id": "wireguard", "mac": SECOND_MAC},
            ]
        )
        domains = _arm_new_template(stub, desktop)

        stub["Cls"].new_template("u1", "tpl-1", "Template", "desktop-1")

        interfaces = _inserted_interfaces(domains)
        assert [i["id"] for i in interfaces] == ["default", "wireguard"]
        macs = [i["mac"] for i in interfaces]
        assert SOURCE_MAC not in macs
        assert SECOND_MAC not in macs
        assert len(set(macs)) == 2

    def test_bare_id_interfaces_become_rows_with_their_own_mac(self, stub):
        desktop = _source_desktop(["default"])
        domains = _arm_new_template(stub, desktop)

        stub["Cls"].new_template("u1", "tpl-1", "Template", "desktop-1")

        assert _inserted_interfaces(domains) == [
            {"id": "default", "mac": "52:54:00:00:00:01"}
        ]

    def test_a_desktop_without_interfaces_stays_without_them(self, stub):
        desktop = _source_desktop([])
        domains = _arm_new_template(stub, desktop)

        stub["Cls"].new_template("u1", "tpl-1", "Template", "desktop-1")

        assert _inserted_interfaces(domains) == []


class TestDuplicateTemplate:
    def _arm(self, stub, interfaces):
        mod, mp = stub["mod"], stub["mp"]
        source = {
            "kind": "template",
            "create_dict": {"hardware": {"interfaces": interfaces}},
        }
        stub["router"](
            "domains"
        ).get.return_value.without.return_value.run.return_value = source
        mp.setattr(
            mod.Helpers,
            "get_user_data",
            classmethod(
                lambda cls, user_id: {
                    "user": "u1",
                    "username": "n",
                    "category": "c1",
                    "group": "g1",
                }
            ),
        )
        return stub["router"]("domains")

    def _duplicated_interfaces(self, domains):
        (inserted,), _ = domains.insert.call_args
        return inserted["create_dict"]["hardware"]["interfaces"]

    def test_the_copy_gets_its_own_macs(self, stub):
        domains = self._arm(stub, [{"id": "default", "mac": SOURCE_MAC}])

        stub["Cls"].duplicate_template({"user_id": "u1"}, "tpl-1", "Copy")

        interfaces = self._duplicated_interfaces(domains)
        assert [i["id"] for i in interfaces] == ["default"]
        assert interfaces[0]["mac"] != SOURCE_MAC

    def test_two_copies_of_the_same_template_do_not_share_a_mac(self, stub):
        domains = self._arm(stub, [{"id": "default", "mac": SOURCE_MAC}])

        stub["Cls"].duplicate_template({"user_id": "u1"}, "tpl-1", "Copy 1")
        first = self._duplicated_interfaces(domains)[0]["mac"]
        stub["Cls"].duplicate_template({"user_id": "u1"}, "tpl-1", "Copy 2")
        second = self._duplicated_interfaces(domains)[0]["mac"]

        assert first != second
