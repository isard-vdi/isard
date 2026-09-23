# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Storage.recreate`` refuses a desktop that declares more than one disk.

The handler that wires the replacement in writes ``create_dict.hardware.disks[0]``
and is given no way to say which disk it is replacing, so recreating the second
disk of a two-disk desktop would point the FIRST one at the blank replacement,
orphan its real storage, and then delete the disk that was actually asked for.
Nothing else in the chain looks at the disk index, so the refusal is the guard.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models import storage as mod
from isardvdi_common.models.storage import Storage


@pytest.fixture
def disk(monkeypatch):
    """An old disk whose recreate preconditions all pass, with a stubbed domain
    whose disk count the test chooses."""
    old = Storage.__new__(Storage)
    old.__dict__.update(
        {
            "id": "old-1",
            "user_id": "u-1",
            "type": "qcow2",
            "parent": "tmpl-1",
            "path": "/isard/groups/old-1.qcow2",
            "directory_path": "/isard/groups",
            "status": "ready",
            "status_logs": [],
        }
    )
    monkeypatch.setattr(
        Storage,
        "__setattr__",
        lambda self, name, value: self.__dict__.__setitem__(name, value),
    )
    monkeypatch.setattr(Storage, "operational", True)
    monkeypatch.setattr(Storage, "exists", staticmethod(lambda _id: True))

    def _set_disks(count):
        dom = MagicMock()
        dom.create_dict = {
            "hardware": {"disks": [{"storage_id": f"d{i}"} for i in range(count)]}
        }
        fake = MagicMock()
        fake.exists.return_value = True
        fake.return_value = dom
        monkeypatch.setattr(mod.domain, "Domain", fake)

    return old, _set_disks


def _recreate(old):
    """Run only as far as the preconditions: the parent read is what stops it."""
    return old.recreate("u-1", "dom-1")


class TestRecreateRefusesAMultiDiskDomain:
    def test_two_disks_are_refused(self, disk, monkeypatch):
        old, set_disks = disk
        set_disks(2)
        with pytest.raises(Error) as exc:
            _recreate(old)
        assert exc.value.error["description_code"] == "multi_disk_recreate_unsupported"
        # The refusal has to BUILD: an unregistered error type raises KeyError
        # out of the catalogue and the guard answers 500 instead of refusing.
        assert exc.value.error["error"] == "bad_request"

    def test_one_disk_is_not_refused_by_this_guard(self, disk, monkeypatch):
        old, set_disks = disk
        set_disks(1)
        # The guard must let it through; what stops the call here is the next
        # step, which this test does not stub.
        monkeypatch.setattr(
            Storage,
            "__init__",
            lambda self, *a, **k: (_ for _ in ()).throw(
                RuntimeError("reached the parent read")
            ),
        )
        with pytest.raises(RuntimeError, match="reached the parent read"):
            _recreate(old)

    def test_a_domain_that_is_gone_is_not_a_refusal(self, disk, monkeypatch):
        old, _ = disk
        fake = MagicMock()
        fake.exists.return_value = False
        monkeypatch.setattr(mod.domain, "Domain", fake)
        monkeypatch.setattr(
            Storage,
            "__init__",
            lambda self, *a, **k: (_ for _ in ()).throw(
                RuntimeError("reached the parent read")
            ),
        )
        with pytest.raises(RuntimeError, match="reached the parent read"):
            _recreate(old)
