# SPDX-License-Identifier: AGPL-3.0-or-later

"""The step that repoints a desktop releases the park it was handed.

A recreate parks the desktop before it starts, and nothing downstream used to
give it back: the chain that replaced the disk left the domain in its lock
status until a self-heal pass finalised it. The repoint is the step that knows
the replacement landed, so it writes the release in the same guarded update.

Also pins why the drop of the old row had to move below the status that
authorises it: ``handle_storage_delete`` only removes a row that already reads
``deleted``, so asking for the drop first silently did nothing.
"""

from unittest.mock import MagicMock, patch

import pytest


def _domain(status):
    d = MagicMock()
    d.status = status
    d.create_dict = {"hardware": {"disks": [{"storage_id": "old-1"}]}}
    return d


def _storage(status="ready"):
    s = MagicMock()
    s.status = status
    s.path = "/isard/groups/new-1.qcow2"
    return s


def _run(domain_status, storage_status="ready"):
    from isardvdi_change_handler.task_results import domain as mod

    with patch.object(
        mod.Domain, "build", return_value=_domain(domain_status)
    ), patch.object(
        mod.Storage, "build", return_value=_storage(storage_status)
    ), patch.object(
        mod.Domain, "update_document_if", return_value=True
    ) as guarded:
        mod.handle_domain_change_storage(MagicMock(), "dom-1", "new-1")
    return guarded


class TestTheRepointReleasesThePark:
    def test_a_parked_desktop_comes_back_stopped(self):
        guarded = _run("Maintenance")
        update = guarded.call_args.args[1]
        assert update["status"] == "Stopped"
        assert update["current_action"] is None
        assert update["create_dict"]["hardware"]["disks"][0]["storage_id"] == "new-1"

    def test_the_release_is_guarded_on_the_status_it_read(self):
        guarded = _run("Maintenance")
        assert guarded.call_args.kwargs["values"] == ("Maintenance",)

    def test_a_creating_desktop_still_advances_instead(self):
        guarded = _run("CreatingDisk")
        assert guarded.call_args.args[1]["status"] == "CreatingDomain"

    def test_a_desktop_in_neither_state_is_only_repointed(self):
        guarded = _run("Stopped")
        assert "status" not in guarded.call_args.args[1]


class TestTheDropNeedsTheStatusFirst:
    @pytest.mark.parametrize(
        "status,dropped", [("deleted", True), ("maintenance", False)]
    )
    def test_a_row_is_dropped_only_once_it_reads_deleted(self, status, dropped):
        from isardvdi_change_handler.task_results import storage as mod

        with patch.object(
            mod.Storage, "delete_document_if", return_value=dropped
        ) as drop:
            mod.handle_storage_delete(MagicMock(), "old-1")
        assert drop.call_args.kwargs["values"] == ("deleted",)
