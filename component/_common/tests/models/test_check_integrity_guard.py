# SPDX-License-Identifier: AGPL-3.0-or-later

"""check_integrity refuses a disk a running desktop holds open (same guard as
repair), and otherwise enqueues a read-only storage_check chain."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models.storage import Storage


def _domains(*statuses):
    return [SimpleNamespace(id=f"d{i}", status=st) for i, st in enumerate(statuses)]


def _self(*domain_statuses):
    return SimpleNamespace(
        id="s1",
        type="qcow2",
        directory_path="/pool/cat/groups",
        path="/pool/cat/groups/s1.qcow2",
        domains=_domains(*domain_statuses),
        create_task=MagicMock(return_value="t1"),
    )


def test_refuses_a_disk_a_started_desktop_holds_open():
    with pytest.raises(Error):
        Storage.check_integrity(_self("Started"), "u1")


def test_enqueues_a_read_only_check_when_nothing_holds_it():
    fake = _self("Stopped")
    with patch("isardvdi_common.models.storage.StoragePool") as pool:
        pool.get_best_for_action.return_value = SimpleNamespace(id="pool1")
        assert Storage.check_integrity(fake, "u1") == "t1"
    kwargs = fake.create_task.call_args.kwargs
    assert kwargs["task"] == "storage_check"
    assert kwargs["dependents"][0]["task"] == "storage_check_result"
