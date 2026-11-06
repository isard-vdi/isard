# SPDX-License-Identifier: AGPL-3.0-or-later

"""A convert that did not finish takes its destination file with it."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PATH = "/isard/groups/u/d.qcow2"


def _run(depending_status, status="deleted", path=PATH, domains=(), exists=True):
    from isardvdi_change_handler.task_results import storage

    task = SimpleNamespace(depending_status=depending_status, user_id="u-1")
    destination = MagicMock(
        path=path,
        status=status,
        domains=list(domains),
        directory_path="/isard/groups/u",
    )
    pool = MagicMock(id="default")
    with (
        patch.object(storage, "Storage") as cls,
        patch.object(storage.StoragePool, "get_best_for_action", return_value=pool),
        patch.object(storage.StoragePool, "mountpoint_for_path", return_value="/isard"),
    ):
        cls.return_value = destination
        cls.exists.return_value = exists
        storage.handle_convert_discard_destination(task, "d", PATH)
    return destination.create_task


@pytest.mark.parametrize("outcome", ["canceled", "failed"])
@pytest.mark.parametrize("status", ["creating", "deleted"])
def test_a_convert_that_did_not_finish_deletes_its_destination(outcome, status):
    create_task = _run(outcome, status=status)
    create_task.assert_called_once()
    kwargs = create_task.call_args.kwargs
    assert kwargs["task"] == "delete"
    assert kwargs["queue"].startswith("storage.default.")
    assert kwargs["job_kwargs"]["kwargs"] == {"path": PATH, "pool_root": "/isard"}
    assert kwargs["user_id"] == "u-1"


def test_a_finished_convert_keeps_its_destination():
    _run("finished").assert_not_called()


@pytest.mark.parametrize("status", ["ready", "downloadable", "maintenance"])
def test_a_destination_that_became_a_disk_is_kept(status):
    _run("canceled", status=status).assert_not_called()


def test_a_row_pointing_elsewhere_is_kept():
    _run("canceled", path="/isard/groups/u/other.qcow2").assert_not_called()


def test_a_destination_a_desktop_uses_is_kept():
    _run("failed", domains=[object()]).assert_not_called()


def test_a_gone_row_queues_nothing():
    _run("failed", exists=False).assert_not_called()


def test_a_lane_that_refuses_is_logged_not_raised():
    from isardvdi_change_handler.task_results import storage

    task = SimpleNamespace(depending_status="failed", user_id="u-1")
    destination = MagicMock(
        path=PATH, status="deleted", domains=[], directory_path="/d"
    )
    destination.create_task.side_effect = RuntimeError("no consumer")
    with (
        patch.object(storage, "Storage") as cls,
        patch.object(storage.StoragePool, "get_best_for_action"),
        patch.object(storage.StoragePool, "mountpoint_for_path"),
    ):
        cls.exists.return_value = True
        cls.return_value = destination
        storage.handle_convert_discard_destination(task, "d", PATH)


def test_the_handler_is_registered():
    from isardvdi_change_handler.task_results import registry, storage

    assert (
        registry.HANDLERS["convert_discard_destination"][0]
        is storage.handle_convert_discard_destination
    )
