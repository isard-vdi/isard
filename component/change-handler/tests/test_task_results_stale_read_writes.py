# SPDX-License-Identifier: AGPL-3.0-or-later

"""Settle-path writes that decide from a row read a moment earlier."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _task(depending_status="finished"):
    return SimpleNamespace(
        id="t1", user_id="u1", depending_status=depending_status, dependencies=[]
    )


def _model_over(store, exists_answer=True):
    """A model whose ``exists`` probe answers from a moment ago."""

    class _Model:
        @staticmethod
        def exists(_item_id):
            return exists_answer

        @staticmethod
        def insert_document(insert_data, *, conflict="error", validate=False):
            store.setdefault(insert_data["id"], {}).update(insert_data)
            return {"inserted": 1}

        @staticmethod
        def update_document(doc_id, update_data, *, validate=True):
            if doc_id not in store:
                return {"skipped": 1, "replaced": 0, "unchanged": 0}
            store[doc_id].update(update_data)
            return {"skipped": 0, "replaced": 1, "unchanged": 0}

    return _Model


@pytest.mark.asyncio
async def test_update_status_does_not_recreate_a_row_deleted_while_the_chain_settled():
    """The probe said the row was there; the recycle bin dropped it since."""
    from isardvdi_change_handler.task_results import storage

    store = {}
    redis_manager = AsyncMock()

    with (
        patch.dict(
            storage._ITEM_CLASS_MAP, {"domain": _model_over(store)}, clear=False
        ),
        patch.object(storage, "send_status_socket", new=AsyncMock()),
    ):
        await storage.handle_update_status(
            redis_manager,
            _task(),
            statuses={"_all": {"Stopped": {"domain": ["d1"]}}},
        )

    assert store == {}, f"a deleted row was resurrected as a zombie: {store}"
