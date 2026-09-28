"""What the engine writes when a disk is not ready, at the call site: the pure
function was never the bug, the branch that used it was."""

import sys
from unittest.mock import MagicMock

import pytest

# conftest stubs `rethinkdb` with a MagicMock, which isardvdi_common cannot
# import from; lift it for this import only.
_rethinkdb_stubs = {
    name: sys.modules.pop(name)
    for name in list(sys.modules)
    if name == "rethinkdb" or name.startswith("rethinkdb.")
}
try:
    import engine.controllers.ui_actions as ui
finally:
    sys.modules.update(_rethinkdb_stubs)

_LOG_STAR_NAMES = {"log": None, "logs": None, "LOG_LEVEL": "INFO"}
for _name, _value in _LOG_STAR_NAMES.items():
    if not hasattr(ui, _name):
        setattr(
            ui,
            _name,
            MagicMock(name=f"ui_actions.{_name}") if _value is None else _value,
        )


@pytest.fixture
def start(monkeypatch):
    """Drive the real start_domain_from_id and hand back the status written."""

    def _run(disk_statuses):
        written = {}

        monkeypatch.setattr(
            ui,
            "get_table_fields",
            lambda *a, **k: {
                "kind": "desktop",
                "name": "d",
                "category": "c",
                "create_dict": {"hardware": {"memory": 1048576}},
                "forced_hyp": False,
                "favourite_hyp": False,
                "hypervisors_pools": ["default"],
                "force_gpus": False,
            },
        )

        storages = [MagicMock(status=status) for status in disk_statuses]
        domain_obj = MagicMock(storages=storages, storage_ready=False)
        domain_cls = MagicMock()
        domain_cls.exists.return_value = True
        domain_cls.return_value = domain_obj
        monkeypatch.setattr(ui, "Domain", domain_cls)

        def _update(status, domain_id, detail=None, **kwargs):
            written["status"] = status
            written["detail"] = detail

        monkeypatch.setattr(ui, "update_domain_status", _update)

        actions = ui.UiActions.__new__(ui.UiActions)
        actions.manager = MagicMock()
        assert actions.start_domain_from_id("desktop-1") is False
        return written

    return _run


def test_a_deleted_disk_is_failed_not_stopped(start):
    written = start(["deleted"])
    assert written["status"] == "Failed"
    assert "deleted" in written["detail"]


@pytest.mark.parametrize("terminal", ["orphan", "broken_chain", "recycled", "failed"])
def test_every_terminal_status_is_failed(start, terminal):
    assert start([terminal])["status"] == "Failed"


@pytest.mark.parametrize("recoverable", ["maintenance", "creating"])
def test_a_recoverable_disk_stays_stopped(start, recoverable):
    written = start([recoverable])
    assert written["status"] == "Stopped"
    assert written["detail"] == "Desktop storage not ready"


def test_non_existing_keeps_its_own_message(start):
    written = start(["non_existing"])
    assert written["status"] == "Failed"
    assert "non existing" in written["detail"]


def test_one_terminal_disk_among_recoverable_ones_still_fails(start):
    written = start(["maintenance", "deleted"])
    assert written["status"] == "Failed"
    assert "deleted" in written["detail"]


def test_the_detail_names_every_blocking_status_once(start):
    written = start(["deleted", "orphan", "deleted"])
    assert (
        written["detail"]
        == "Desktop storage is deleted, orphan and will not become ready"
    )


class _ReachedXml(BaseException):
    """Escapes the `except Exception` around the xml call."""


@pytest.fixture
def finish_update(monkeypatch):
    """Drive updating_from_create_dict_th and hand back the status written."""

    def _run(disk_statuses, kind="desktop"):
        written = {}

        monkeypatch.setattr(
            ui,
            "get_table_fields",
            lambda *a, **k: {
                "kind": kind,
                "name": "d",
                "create_dict": {"hardware": {"memory": 1048576}},
                "forced_hyp": False,
                "favourite_hyp": False,
                "hypervisors_pools": ["default"],
            },
        )
        storages = [MagicMock(status=status) for status in disk_statuses]
        domain_cls = MagicMock()
        domain_cls.return_value = MagicMock(storages=storages)
        monkeypatch.setattr(ui, "Domain", domain_cls)

        def _update(status, domain_id, detail=None, **kwargs):
            written["status"] = status
            written["detail"] = detail

        monkeypatch.setattr(ui, "update_domain_status", _update)
        # The xml call is wrapped in `except Exception`, so the sentinel has to
        # be a BaseException to escape it and prove the guard let the call through.
        monkeypatch.setattr(
            ui, "recreate_xml_to_start", MagicMock(side_effect=_ReachedXml())
        )
        monkeypatch.setattr(ui, "sleep", lambda *_: None)

        actions = ui.UiActions.__new__(ui.UiActions)
        actions.manager = MagicMock()
        return actions.updating_from_create_dict_th("desktop-1"), written

    return _run


@pytest.mark.parametrize("terminal", ["deleted", "orphan", "broken_chain", "recycled"])
def test_a_hardware_edit_does_not_leave_a_terminal_disk_stopped(
    finish_update, terminal
):
    result, written = finish_update([terminal])
    assert result is False
    assert written["status"] == "Failed"
    assert terminal in written["detail"]


@pytest.mark.parametrize("recoverable", ["maintenance", "creating"])
def test_a_hardware_edit_over_a_recoverable_disk_carries_on(finish_update, recoverable):
    with pytest.raises(_ReachedXml):
        finish_update([recoverable])


def test_a_ready_disk_carries_on_too(finish_update):
    with pytest.raises(_ReachedXml):
        finish_update(["ready"])
