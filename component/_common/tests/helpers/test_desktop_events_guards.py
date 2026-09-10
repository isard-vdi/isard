# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guard paths of ``DesktopEvents`` lifecycle in ``desktop_events.py``.

* ``get_desktop`` -- any lookup failure surfaces as ``not_found``.
* ``desktop_start`` -- returns early (no write) when already started; refuses a
  status it can't start from and an un-ready storage (``precondition_required``).
* ``desktop_stop`` -- returns early (no write) when already stopped; refuses a
  status it can't stop from.

Only rethink and the ``Domain`` model / ``Caches`` are stubbed; the state
decision is the code's. Guards assert the ``Error`` type + ``description_code``
and that no status write happened.
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
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    monkeypatch.setattr(
        mod.Caches, "get_document", classmethod(lambda cls, *a, **k: "user")
    )
    dom = MagicMock(name="Domain")
    dom.return_value.storage_ready = True
    monkeypatch.setattr(mod, "Domain", dom)
    return {
        "mod": mod,
        "Cls": mod.DesktopEvents,
        "table": mock_table,
        "mp": monkeypatch,
        "Domain": dom,
    }


def _get_desktop_returns(stub, domain):
    # get_desktop: r.table("domains").get(id).pluck("status","create_dict","user").run()
    stub["table"].return_value.get.return_value.pluck.return_value.run.return_value = (
        domain
    )


def _stop_status(stub, status):
    # desktop_stop: r.table("domains").get(id).pluck("status")["status"].run()
    stub[
        "table"
    ].return_value.get.return_value.pluck.return_value.__getitem__.return_value.run.return_value = (
        status
    )


def _no_update(stub):
    stub["table"].return_value.get.return_value.update.assert_not_called()


class TestGetDesktop:
    def test_lookup_failure_is_not_found(self, stub):
        stub[
            "table"
        ].return_value.get.return_value.pluck.return_value.run.side_effect = RuntimeError(
            "gone"
        )
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].get_desktop("nope")
        assert exc.value.error["error"] == "not_found"
        assert exc.value.error["description_code"] == "not_found"


class TestDesktopStart:
    def _domain(self, status):
        return {"status": status, "create_dict": {"hardware": {}}, "user": "u1"}

    def test_already_started_returns_without_writing(self, stub):
        _get_desktop_returns(stub, self._domain("Started"))
        assert stub["Cls"].desktop_start("d1") == "Started"
        _no_update(stub)

    def test_invalid_status_refused(self, stub):
        _get_desktop_returns(stub, self._domain("Creating"))
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].desktop_start("d1")
        assert exc.value.error["description_code"] == "unable_to_start_desktop_from"
        _no_update(stub)

    def test_storage_not_ready_refused(self, stub):
        _get_desktop_returns(stub, self._domain("Stopped"))
        stub["Domain"].return_value.storage_ready = False
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].desktop_start("d1")
        assert exc.value.error["description_code"] == "desktop_storage_not_ready"
        _no_update(stub)


class TestDesktopStop:
    def test_already_stopped_returns_without_writing(self, stub):
        _stop_status(stub, "Stopped")
        assert stub["Cls"].desktop_stop("d1") == "Stopped"
        _no_update(stub)

    def test_invalid_status_refused(self, stub):
        _stop_status(stub, "Creating")
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].desktop_stop("d1")
        assert exc.value.error["description_code"] == "unable_to_stop_desktop_from"
        _no_update(stub)
