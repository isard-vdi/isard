# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shutdown, stop and reset sent to a hypervisor the engine has no worker for."""

import sys
from unittest.mock import MagicMock

import pytest

_rethinkdb_stubs = {
    name: sys.modules.pop(name)
    for name in list(sys.modules)
    if name == "rethinkdb" or name.startswith("rethinkdb.")
}
try:
    import engine.controllers.ui_actions as ui
finally:
    sys.modules.update(_rethinkdb_stubs)

if not hasattr(ui, "logs"):
    ui.logs = MagicMock(name="ui_actions.logs")

ACTIONS = ["shutdown_domain", "stop_domain", "reset_domain"]


@pytest.fixture
def ui_actions(monkeypatch):
    status = MagicMock(name="update_domain_status")
    monkeypatch.setattr(ui, "update_domain_status", status)
    actions = ui.UiActions.__new__(ui.UiActions)
    actions.manager = MagicMock()
    actions.manager.q.workers = {"hyp-live": MagicMock(name="queue")}
    return actions, status


@pytest.mark.parametrize("method", ACTIONS)
def test_missing_worker_marks_the_desktop_instead_of_raising(ui_actions, method):
    actions, status = ui_actions

    assert getattr(actions, method)("desktop-1", "hyp-gone") is False

    status.assert_called_once()
    kwargs = status.call_args.kwargs
    assert kwargs["status"] == "Unknown"
    assert kwargs["id_domain"] == "desktop-1"
    assert "hyp-gone" in kwargs["detail"]


@pytest.mark.parametrize("method", ACTIONS)
def test_live_worker_gets_the_action(ui_actions, method):
    actions, status = ui_actions

    assert getattr(actions, method)("desktop-1", "hyp-live") is True

    queue = actions.manager.q.workers["hyp-live"]
    queue.put.assert_called_once()
    action = queue.put.call_args.args[0]
    assert action["type"] == method
    assert action["id_domain"] == "desktop-1"
    status.assert_not_called()
