# SPDX-License-Identifier: AGPL-3.0-or-later

"""A resize that fails must release the storage from maintenance.

`increase_size` puts the storage (and its domains) into maintenance before
enqueuing, but its chain only ever wrote a status on the SUCCESS path: the
backing-chain step feeding `storage_update`. A failed or cancelled resize
therefore stopped silently and left the row in `maintenance` for ever - the
disk untouched, but the user unable to do anything else with it, and the real
cause invisible.
"""

from __future__ import annotations

import inspect


def _chain_source():
    from isardvdi_common.models.storage import Storage

    return inspect.getsource(Storage.increase_size)


class TestResizeHasTerminalReleaseBranches:
    def test_chain_declares_an_update_status_step(self):
        assert '"task": "update_status"' in _chain_source()

    def test_failure_and_cancel_release_the_storage(self):
        from isardvdi_common.models.storage import Storage

        statuses = Storage._maintenance_release_statuses("s1", ["d1", "d2"])

        assert statuses["failed"]["ready"]["storage"] == ["s1"]
        assert statuses["canceled"]["ready"]["storage"] == ["s1"]
        assert statuses["failed"]["Stopped"]["domain"] == ["d1", "d2"]
        assert statuses["canceled"]["Stopped"]["domain"] == ["d1", "d2"]

    def test_success_is_not_claimed_here(self):
        """The success side belongs to the chain's own backing-chain update;
        naming it twice would race two writers on the same row."""
        from isardvdi_common.models.storage import Storage

        statuses = Storage._maintenance_release_statuses("s1", [])

        assert "finished" not in statuses
        assert "_all" not in statuses
