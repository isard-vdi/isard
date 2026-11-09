# SPDX-License-Identifier: AGPL-3.0-or-later

"""A migration parks a disk only from the status it recorded, so it never moves one a dig holds."""

import pytest
from isardvdi_common.lib.storage import migration_run as mr


class _Storage:
    status = "ready"
    calls = []
    #: another task parks the disk between the migration's read and its park
    dig_parks_first = False

    def __init__(self, sid):
        self.id = sid

    @classmethod
    def update_document_if(cls, sid, fields, *, field, values, validate=True):
        cls.calls.append(("if", sid, fields, values))
        if cls.dig_parks_first:
            cls.status = "maintenance"
        if cls.status not in values:
            return False
        cls.status = fields["status"]
        return True

    @classmethod
    def update_document(cls, sid, fields, validate=True):
        cls.calls.append(("always", sid, fields))
        cls.status = fields["status"]


@pytest.fixture
def runner(monkeypatch):
    _Storage.status = "ready"
    _Storage.calls = []
    _Storage.dig_parks_first = False
    monkeypatch.setattr(mr, "Storage", _Storage)
    r = object.__new__(mr.MigrationRunner)
    r.failed = []
    r.parked_domains = []
    r._set = lambda item, **f: item.update(f)
    r._fail = lambda item: r.failed.append(item["storage_id"])
    r._park_domains = lambda item: r.parked_domains.append(item["storage_id"])
    return r


def test_a_ready_disk_is_parked_from_ready(runner):
    item = {"storage_id": "s1"}
    assert runner._prepare_disk_for_move(item) is True
    assert item["storage_orig_status"] == "ready"
    assert _Storage.status == "maintenance"
    assert _Storage.calls == [("if", "s1", {"status": "maintenance"}, ("ready",))]
    assert runner.parked_domains == ["s1"]


def test_a_disk_a_dig_parked_in_between_is_refused_not_moved(runner):
    _Storage.dig_parks_first = True
    item = {"storage_id": "s1"}
    assert runner._prepare_disk_for_move(item) is False
    assert runner.failed == ["s1"]
    assert "another task parked" in item["error"]
    assert runner.parked_domains == []
    assert not [c for c in _Storage.calls if c[0] == "always"]


def test_a_disk_already_in_maintenance_is_refused(runner):
    _Storage.status = "maintenance"
    item = {"storage_id": "s1"}
    assert runner._prepare_disk_for_move(item) is False
    assert runner.failed == ["s1"]
    assert _Storage.calls == []


def test_a_resumed_item_parks_its_disk_again(runner):
    _Storage.status = "maintenance"
    item = {"storage_id": "s1", "storage_orig_status": "recycled"}
    assert runner._prepare_disk_for_move(item) is True
    assert _Storage.calls == [("always", "s1", {"status": "maintenance"})]
    assert runner.parked_domains == ["s1"]
