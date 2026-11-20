# SPDX-License-Identifier: AGPL-3.0-or-later

"""Model tests neutralise the on-disk children guard by default (it needs a live lane and Redis); the ``on_disk_guard`` marker opts back into the real one."""

import pytest
from isardvdi_common.models.storage import Storage


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "on_disk_guard: exercise the real qcow2-header children guard (ticket 7747)",
    )


@pytest.fixture(autouse=True)
def _neutralise_on_disk_children_guard(request, monkeypatch):
    if request.node.get_closest_marker("on_disk_guard"):
        return
    monkeypatch.setattr(
        Storage, "_blocks_on_header_dependents", lambda self, action: False
    )
