#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A task result for a row deleted meanwhile must not bring the row back."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from isardvdi_change_handler.task_results import media as media_results
from isardvdi_change_handler.task_results import storage as storage_results
from isardvdi_common.models.domain import Domain
from isardvdi_common.models.media import Media
from rethinkdb import r

pytestmark = pytest.mark.real


def _task():
    return SimpleNamespace(depending_status="finished", dependencies=[], id="t")


def _row(table, doc_id):
    with Domain._rdb_context():
        return r.table(table).get(doc_id).run(Domain._rdb_connection)


def _insert(table, doc):
    with Domain._rdb_context():
        r.table(table).insert(doc).run(Domain._rdb_connection)


def _delete(table, doc_id):
    with Domain._rdb_context():
        r.table(table).get(doc_id).delete().run(Domain._rdb_connection)


def test_a_domain_deleted_after_the_check_stays_deleted():
    doc_id = str(uuid.uuid4())
    _insert("domains", {"id": doc_id, "kind": "desktop", "status": "Stopped"})
    _delete("domains", doc_id)

    with patch.object(Domain, "exists", return_value=True):
        asyncio.run(
            storage_results.handle_update_status(
                AsyncMock(),
                _task(),
                statuses={"_all": {"Failed": {"domain": [doc_id]}}},
            )
        )

    assert _row("domains", doc_id) is None


def test_a_live_domain_still_gets_its_status():
    doc_id = str(uuid.uuid4())
    _insert("domains", {"id": doc_id, "kind": "desktop", "status": "Stopped"})
    try:
        asyncio.run(
            storage_results.handle_update_status(
                AsyncMock(),
                _task(),
                statuses={"_all": {"Failed": {"domain": [doc_id]}}},
            )
        )
        assert _row("domains", doc_id)["status"] == "Failed"
    finally:
        _delete("domains", doc_id)


def test_a_media_deleted_while_downloading_stays_deleted():
    doc_id = str(uuid.uuid4())
    _insert("media", {"id": doc_id, "kind": "iso", "status": "Downloading"})
    _delete("media", doc_id)

    with patch.object(Media, "exists", return_value=True):
        media_results.handle_media_update(_task(), id=doc_id, status="Downloaded")

    assert _row("media", doc_id) is None
