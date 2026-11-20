# SPDX-License-Identifier: AGPL-3.0-or-later

"""The children guard refuses an on-disk qcow2-header child the DB does not record, and fails closed when the worker cannot answer."""

from unittest.mock import MagicMock, patch

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.storage.storage import StorageProcessed
from isardvdi_common.models.storage import Storage

pytestmark = pytest.mark.on_disk_guard

_SCAN = "scan_on_disk_dependents"


def _bare(monkeypatch, status="ready", domains=(), children=()):
    monkeypatch.setattr(Storage, "__setattr__", object.__setattr__)
    monkeypatch.setattr(Storage, "domains", property(lambda self: list(domains)))
    monkeypatch.setattr(Storage, "children", property(lambda self: list(children)))
    storage = Storage.__new__(Storage)
    storage.__dict__["id"] = "s-1"
    storage.__dict__["status"] = status
    storage.__dict__["directory_path"] = "/isard/templates/cat/grp"
    storage.__dict__["type"] = "qcow2"
    return storage


def _code(excinfo):
    err = excinfo.value
    return getattr(err, "description_code", None) or (
        err.error.get("description_code")
        if isinstance(getattr(err, "error", None), dict)
        else None
    )


def _result(dependents=(), unreadable=(), ok=True, reason=None):
    return {
        "dependents": list(dependents),
        "unreadable": list(unreadable),
        "ok": ok,
        "reason": reason,
    }


@pytest.mark.parametrize("action", ["sparsify", "move"])
def test_a_header_only_child_refuses(action, monkeypatch):
    """DB has no children, the worker finds one in a qcow2 header: refuse."""
    storage = _bare(monkeypatch)
    scan = MagicMock(
        return_value=_result(dependents=["/isard/templates/cat/grp/c.qcow2"])
    )
    with patch.object(StorageProcessed, _SCAN, scan, create=True):
        with pytest.raises(Error) as excinfo:
            storage.set_maintenance(action)
    assert _code(excinfo) == "storage_has_children"
    scan.assert_called()  # the DB said no, so the disk was consulted


@pytest.mark.parametrize("reason", ["timeout", "no_consumer", "task_failed"])
def test_an_untrustworthy_scan_fails_closed(reason, monkeypatch):
    """No lane consumer / task failed / deadline passed: treat as "has children"."""
    storage = _bare(monkeypatch)
    scan = MagicMock(return_value=_result(ok=False, reason=reason))
    with patch.object(StorageProcessed, _SCAN, scan, create=True):
        with pytest.raises(Error) as excinfo:
            storage.set_maintenance("sparsify")
    assert _code(excinfo) == "storage_has_children"


def test_an_unreadable_candidate_fails_closed(monkeypatch):
    """A qcow2 whose header would not read might be a child we cannot see:
    refuse rather than risk corrupting it."""
    storage = _bare(monkeypatch)
    scan = MagicMock(
        return_value=_result(unreadable=["/isard/templates/cat/grp/x.qcow2"])
    )
    with patch.object(StorageProcessed, _SCAN, scan, create=True):
        with pytest.raises(Error) as excinfo:
            storage.set_maintenance("sparsify")
    assert _code(excinfo) == "storage_has_children"


def test_no_child_anywhere_admits(monkeypatch):
    """DB empty and the worker finds nothing: the guard admits (``_refusal`` is
    None), having consulted the disk exactly because the DB said no."""
    storage = _bare(monkeypatch)
    scan = MagicMock(return_value=_result())
    with patch.object(StorageProcessed, _SCAN, scan, create=True):
        assert storage._refusal("sparsify", "ready") is None
    scan.assert_called_once()


def test_a_db_child_refuses_without_touching_the_disk(monkeypatch):
    """DB-first: a child recorded in the DB refuses without a worker round-trip."""
    storage = _bare(monkeypatch, children=["child-db"])
    scan = MagicMock(return_value=_result())
    with patch.object(StorageProcessed, _SCAN, scan, create=True):
        with pytest.raises(Error) as excinfo:
            storage.set_maintenance("sparsify")
    assert _code(excinfo) == "storage_has_children"
    scan.assert_not_called()


def test_the_disk_is_scanned_once_per_operation(monkeypatch):
    """guard() and set_maintenance() both reach _refusal, so the on-disk answer
    is memoised on the instance: one worker round-trip per operation, not two."""
    storage = _bare(monkeypatch)
    scan = MagicMock(return_value=_result())
    with patch.object(StorageProcessed, _SCAN, scan, create=True):
        assert storage._blocks_on_header_dependents("sparsify") is False
        assert storage._blocks_on_header_dependents("move") is False
    scan.assert_called_once()
