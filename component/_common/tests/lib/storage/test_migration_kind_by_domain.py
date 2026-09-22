# SPDX-License-Identifier: AGPL-3.0-or-later

"""A plan classifies a disk by the domain that uses it, and says why a disk stays."""

from isardvdi_common.lib.storage import migration as mig


class _Pool:
    id = "dst"
    mountpoint = "/dst"

    def get_usage_path(self, usage):
        return {"desktop": "groups", "template": "templates"}[usage]


class _FakeStorage:
    registry: dict = {}

    @classmethod
    def exists(cls, sid):
        return sid in cls.registry

    def __init__(self, sid):
        data = _FakeStorage.registry[sid]
        self.id = sid
        self.type = "qcow2"
        self.parent = data.get("parent")
        self.perms = data.get("perms", ["r"])
        self.pool_usage = data.get("pool_usage", "desktop")
        self._children_ids = data.get("children", [])

    @property
    def children(self):
        return [_FakeStorage(c) for c in self._children_ids]

    @property
    def path(self):
        return f"/src/{self.id}.qcow2"

    def get_storage_pool_path(self, pool):
        return f"{pool.mountpoint}/{pool.get_usage_path(self.pool_usage)}"


class _FakeStorageProcessed:
    @staticmethod
    def get_storage_actual_size(sid):
        return 1000


def _plan(monkeypatch, registry, domains, item_kinds):
    _FakeStorage.registry = registry
    monkeypatch.setattr("isardvdi_common.models.storage.Storage", _FakeStorage)
    monkeypatch.setattr(
        "isardvdi_common.lib.storage.storage.StorageProcessed", _FakeStorageProcessed
    )
    asked = []

    def _kinds(storage_ids):
        asked.append(set(storage_ids))
        return {sid: set(k) for sid, k in domains.items()}

    monkeypatch.setattr(mig, "domain_kinds_by_storage", _kinds)
    roots = [sid for sid, data in registry.items() if not data.get("parent")]
    items, totals = mig.build_plan_for_roots("m", roots, _Pool(), item_kinds=item_kinds)
    return items, totals, asked


def test_a_writable_leaf_used_by_a_template_does_not_move_as_a_desktop(monkeypatch):
    """The field case: a template with no derivatives left carries the
    write-permission marker from a 2024 schema migration and, on the marker
    alone, «move only desktops» moved it."""
    items, totals, _ = _plan(
        monkeypatch,
        {"t": {"perms": ["r", "w"], "pool_usage": "template"}},
        {"t": {"template"}},
        ["desktop"],
    )
    assert items == []
    assert totals["not_moving_by_kind"] == {"template": 1}
    (stay,) = totals["not_moving_disks"]
    assert stay["storage_id"] == "t"
    assert stay["kind"] == "template"
    assert stay["classified_by"] == "domain"
    assert "template" in stay["reason"] and "desktop" in stay["reason"]


def test_a_read_only_leaf_used_by_a_desktop_moves_as_a_desktop(monkeypatch):
    """A template converted into a desktop keeps its read-only marker; on the
    marker alone «move only desktops» never moved it."""
    items, totals, _ = _plan(
        monkeypatch,
        {"d": {"perms": ["r"], "pool_usage": "desktop"}},
        {"d": {"desktop"}},
        ["desktop"],
    )
    assert [it["storage_id"] for it in items] == ["d"]
    assert items[0]["kind"] == "desktop"
    assert totals["not_moving_disks"] == []


def test_a_disk_without_a_domain_is_classified_by_its_directory(monkeypatch):
    items, totals, _ = _plan(
        monkeypatch,
        {"rb": {"perms": ["r"], "pool_usage": "desktop"}},
        {},
        ["template"],
    )
    assert items == []
    (stay,) = totals["not_moving_disks"]
    assert (stay["kind"], stay["classified_by"]) == ("desktop", "path")


def test_the_domains_are_looked_up_once_for_the_whole_walk(monkeypatch):
    _, _, asked = _plan(
        monkeypatch,
        {
            "root": {"pool_usage": "template", "children": ["a", "b"]},
            "a": {"parent": "root"},
            "b": {"parent": "root"},
        },
        {"root": {"template"}, "a": {"desktop"}, "b": {"desktop"}},
        [],
    )
    assert asked == [{"root", "a", "b"}]


def test_everything_moves_when_no_kind_is_selected(monkeypatch):
    items, totals, _ = _plan(
        monkeypatch,
        {
            "root": {"pool_usage": "template", "children": ["a"]},
            "a": {"parent": "root"},
        },
        {"root": {"template"}, "a": {"desktop"}},
        [],
    )
    assert sorted(it["storage_id"] for it in items) == ["a", "root"]
    assert totals["not_moving_disks"] == [] and totals["not_moving_total"] == 0
