#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A category that leaves or comes back must resync the portal's domain maps."""

import threading
from unittest.mock import MagicMock

import isardvdi_common.helpers.bastion as bastion_module
import pytest
from isardvdi_common.helpers.bastion import Bastion

PUBLISHED = {
    "id": "cat-1",
    "name": "Tenant",
    "branding": {"domain": {"enabled": True, "name": "tenant.example.org"}},
}
BASTION_ONLY = {"id": "cat-2", "name": "Lab", "bastion_domain": "lab.example.org"}
PLAIN = {"id": "cat-3", "name": "Plain"}


class _Ctx:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture(autouse=True)
def _reset_state():
    yield
    bastion_module._haproxy_bastion_client_provider = None
    bastion_module._category_resync_state.update(running=False, pending=False)


@pytest.fixture
def resyncs(monkeypatch):
    calls = []
    monkeypatch.setattr(
        Bastion,
        "resync_category_domains_in_background",
        classmethod(lambda cls: calls.append(True) or True),
    )
    return calls


class TestCategoryPublishesDomains:
    @pytest.mark.parametrize(
        "category, expected",
        [
            (PUBLISHED, True),
            (BASTION_ONLY, True),
            (PLAIN, False),
            (None, False),
            ({"branding": {"domain": {"enabled": False, "name": "x.org"}}}, False),
            ({"branding": {"domain": {"enabled": True, "name": ""}}}, False),
            ({"bastion_domain": None}, False),
        ],
    )
    def test_truth_table(self, category, expected):
        assert Bastion.category_publishes_domains(category) is expected


class TestBackgroundResync:
    def test_without_haproxy_client_nothing_starts(self, monkeypatch):
        monkeypatch.setattr(
            bastion_module.threading,
            "Thread",
            MagicMock(side_effect=AssertionError("no thread without a client")),
        )
        assert Bastion.resync_category_domains_in_background() is False

    def test_both_maps_are_pushed_and_errors_do_not_escape(self, monkeypatch):
        pushed = []

        def domains():
            pushed.append("domains")
            raise RuntimeError("portal down")

        def maps():
            pushed.append("maps")
            raise RuntimeError("portal down")

        monkeypatch.setattr(Bastion, "sync_category_branding_domains", domains)
        monkeypatch.setattr(Bastion, "update_bastion_haproxy_map", maps)
        bastion_module._category_resync_state["running"] = True

        Bastion._resync_category_domains_until_idle()

        assert pushed == ["domains", "maps"]
        assert bastion_module._category_resync_state["running"] is False

    def test_a_burst_of_writes_costs_one_extra_round(self, monkeypatch):
        bastion_module._haproxy_bastion_client_provider = lambda: object()
        release = threading.Event()
        started = threading.Event()
        rounds = []

        def domains():
            rounds.append(True)
            started.set()
            release.wait(5)

        monkeypatch.setattr(Bastion, "sync_category_branding_domains", domains)
        monkeypatch.setattr(Bastion, "update_bastion_haproxy_map", lambda: None)

        assert Bastion.resync_category_domains_in_background() is True
        assert started.wait(5)
        for _ in range(5):
            assert Bastion.resync_category_domains_in_background() is True
        release.set()

        for _ in range(500):
            if not bastion_module._category_resync_state["running"]:
                break
            threading.Event().wait(0.01)
        assert bastion_module._category_resync_state["running"] is False
        assert len(rounds) == 2


@pytest.fixture
def rb_mod(monkeypatch):
    from isardvdi_common.helpers import recycle_bin as mod

    monkeypatch.setattr(mod.RethinkSharedConnection, "_rdb_context", _Ctx)
    return mod


def _route_tables(mod, monkeypatch, rows, broken=()):
    made = {}

    def _table(name):
        if name in broken:
            raise _Stop(name)
        if name not in made:
            table = MagicMock(name=f"table-{name}")
            table.get.return_value.run.return_value = rows.get(name)
            made[name] = table
        return made[name]

    monkeypatch.setattr(mod.r, "table", _table)
    return made


class _Stop(Exception):
    pass


def _recycle_category(mod, monkeypatch, category):
    _route_tables(mod, monkeypatch, {"categories": category})
    monkeypatch.setattr(mod.RecycleBinCategory, "add_category", lambda s, c: None)
    monkeypatch.setattr(mod.RecycleBinCategory, "_add_item_name", lambda s, n: None)
    monkeypatch.setattr(mod.RecycleBin, "_add_owner", lambda s, o: None)
    monkeypatch.setattr(mod.RecycleBinCategory, "_set_data", lambda s, i: "rb-1")
    rb = object.__new__(mod.RecycleBinCategory)
    rb.id, rb.agent_id, rb.item_name = "rb-1", "admin", None
    return rb.add(category["id"])


class TestRecycleBinCategory:
    def test_recycling_a_category_with_a_domain_resyncs(
        self, rb_mod, monkeypatch, resyncs
    ):
        assert _recycle_category(rb_mod, monkeypatch, PUBLISHED) == "rb-1"
        assert resyncs == [True]

    def test_recycling_a_category_with_a_bastion_domain_resyncs(
        self, rb_mod, monkeypatch, resyncs
    ):
        _recycle_category(rb_mod, monkeypatch, BASTION_ONLY)
        assert resyncs == [True]

    def test_recycling_a_plain_category_does_not(self, rb_mod, monkeypatch, resyncs):
        _recycle_category(rb_mod, monkeypatch, PLAIN)
        assert resyncs == []


class TestRestore:
    def _restore(self, mod, monkeypatch, categories):
        _route_tables(mod, monkeypatch, {}, broken=("storage",))
        monkeypatch.setattr(mod, "_exists_now", lambda table, item_id: True)
        monkeypatch.setattr(mod.RecycleBin, "check_can_restore", lambda s: None)
        monkeypatch.setattr(
            mod.Helpers, "claim_status", classmethod(lambda cls, *a: True)
        )
        rb = object.__new__(mod.RecycleBin)
        rb.id, rb.item_type, rb.owner_id, rb.owner_name = "rb-1", "category", "u", "u"
        rb.status = mod.RecycleBinStatusEnum.recycled.value
        rb.users, rb.groups, rb.categories = [], [], categories
        rb.storages = []
        with pytest.raises(Exception):
            rb.restore()
        assert mod.r.table("users").insert.called

    def test_restoring_a_category_with_a_domain_resyncs(
        self, rb_mod, monkeypatch, resyncs
    ):
        self._restore(rb_mod, monkeypatch, [PLAIN, PUBLISHED])
        assert resyncs == [True]

    def test_restoring_only_plain_categories_does_not(
        self, rb_mod, monkeypatch, resyncs
    ):
        self._restore(rb_mod, monkeypatch, [PLAIN])
        assert resyncs == []


@pytest.fixture
def api_admin(monkeypatch):
    from isardvdi_common.lib import api_admin as mod

    monkeypatch.setattr(mod.RethinkSharedConnection, "_rdb_context", _Ctx)
    monkeypatch.setattr(mod.ApiAdmin, "_validate_table", classmethod(lambda c, t: None))
    return mod


def _admin_rows(mod, monkeypatch, before, after):
    table = MagicMock(name="table")
    table.get.return_value.run.side_effect = [before, after]
    table.insert.return_value.run.return_value = {"inserted": 1}
    table.get.return_value.delete.return_value.run.return_value = {"deleted": 1}
    monkeypatch.setattr(mod.r, "table", lambda name: table)
    return table


class TestAdminTableWrites:
    def test_disabling_a_domain_through_the_table_resyncs(
        self, api_admin, monkeypatch, resyncs
    ):
        _admin_rows(api_admin, monkeypatch, PUBLISHED, PLAIN)
        api_admin.ApiAdmin.update_table_item("categories", {"id": "cat-1"})
        assert resyncs == [True]

    def test_enabling_a_domain_through_the_table_resyncs(
        self, api_admin, monkeypatch, resyncs
    ):
        _admin_rows(api_admin, monkeypatch, PLAIN, PUBLISHED)
        api_admin.ApiAdmin.update_table_item("categories", {"id": "cat-1"})
        assert resyncs == [True]

    def test_editing_a_plain_category_does_not(self, api_admin, monkeypatch, resyncs):
        _admin_rows(api_admin, monkeypatch, PLAIN, PLAIN)
        api_admin.ApiAdmin.update_table_item("categories", {"id": "cat-3"})
        assert resyncs == []

    def test_deleting_a_category_row_with_a_domain_resyncs(
        self, api_admin, monkeypatch, resyncs
    ):
        _admin_rows(api_admin, monkeypatch, PUBLISHED, None)
        api_admin.ApiAdmin.delete_table_item("categories", "cat-1")
        assert resyncs == [True]

    def test_inserting_a_category_with_a_domain_resyncs(
        self, api_admin, monkeypatch, resyncs
    ):
        _admin_rows(api_admin, monkeypatch, None, None)
        api_admin.ApiAdmin.insert_table_item("categories", dict(PUBLISHED))
        assert resyncs == [True]

    def test_other_tables_never_resync(self, api_admin, monkeypatch, resyncs):
        _admin_rows(api_admin, monkeypatch, PUBLISHED, PUBLISHED)
        api_admin.ApiAdmin.update_table_item("interfaces", {"id": "x"})
        assert resyncs == []
