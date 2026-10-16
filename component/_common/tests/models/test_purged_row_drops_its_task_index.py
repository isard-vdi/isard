# SPDX-License-Identifier: AGPL-3.0-or-later

"""Purging a storage or media row also drops its ``<kind>:<id>:tasks`` index."""

from unittest.mock import MagicMock, patch

import pytest
from isardvdi_common.connections.rethink_base import RethinkBase
from isardvdi_common.models.media import Media
from isardvdi_common.models.storage import Storage
from isardvdi_common.models.task import Task


@pytest.fixture
def redis():
    fake = MagicMock()
    with patch.object(Task, "_redis", fake):
        yield fake


def _rows_deleted(deleted):
    return (
        patch.object(RethinkBase, "delete", classmethod(lambda cls, _id: deleted)),
        patch.object(
            RethinkBase,
            "delete_document_if",
            classmethod(lambda cls, _id, *, field, values: deleted),
        ),
    )


@pytest.mark.parametrize(
    "model, key", [(Storage, "storage:row-1:tasks"), (Media, "media:row-1:tasks")]
)
class TestPurge:
    def test_delete_drops_the_index(self, redis, model, key):
        plain, guarded = _rows_deleted(True)
        with plain, guarded:
            assert model.delete("row-1") is True
        redis.unlink.assert_called_once_with(key)

    def test_guarded_delete_drops_the_index(self, redis, model, key):
        plain, guarded = _rows_deleted(True)
        with plain, guarded:
            assert model.delete_document_if(
                "row-1", field="status", values=("deleted",)
            )
        redis.unlink.assert_called_once_with(key)

    def test_a_row_that_was_not_deleted_keeps_its_index(self, redis, model, key):
        plain, guarded = _rows_deleted(False)
        with plain, guarded:
            assert model.delete("row-1") is False
            assert not model.delete_document_if(
                "row-1", field="status", values=("deleted",)
            )
        redis.unlink.assert_not_called()

    def test_a_redis_failure_does_not_fail_the_purge(self, redis, model, key):
        redis.unlink.side_effect = ConnectionError("redis gone")
        plain, guarded = _rows_deleted(True)
        with plain, guarded:
            assert model.delete("row-1") is True
