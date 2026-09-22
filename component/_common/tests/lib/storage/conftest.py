# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest


@pytest.fixture(autouse=True)
def system_delete_action_is_move(monkeypatch):
    """The release reads the recycle bin's global delete action from the DB;
    pin it to the park so a suite with no DB behind it never depends on what a
    mock answers. A test about the resolution sets its own on the instance."""
    from isardvdi_common.lib.storage import migration_run as mr

    monkeypatch.setattr(
        mr.MigrationRunner, "_system_delete_action", staticmethod(lambda: "move")
    )
