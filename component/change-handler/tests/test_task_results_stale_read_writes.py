# SPDX-License-Identifier: AGPL-3.0-or-later

"""Settle-path writes that decide from a row read a moment earlier."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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


def _storage_over(store, storage_obj):
    """A Storage class whose guarded writes are honoured against ``store``."""

    class _Storage:
        @staticmethod
        def exists(_storage_id):
            return True

        def __new__(cls, _storage_id=None):
            return storage_obj

        @staticmethod
        def write_reading(reading, observer=False, read_at=None):
            return reading.get("status")

        @staticmethod
        def update_document(doc_id, update_data, *, validate=True):
            store.setdefault(doc_id, {}).update(update_data)
            return {"replaced": 1}

        @staticmethod
        def update_document_if(
            doc_id, update_data, *, field, values=None, excluding=None, validate=True
        ):
            held = store.get(doc_id, {}).get(field)
            if (values is not None and held not in values) or (
                excluding is not None and held in excluding
            ):
                return False
            store.setdefault(doc_id, {}).update(update_data)
            return True

    return _Storage


def _read_row(store, doc_id, read_status):
    """A row as the walk read it, over a store that has since moved on."""

    class _Row:
        def __init__(self):
            object.__setattr__(self, "id", doc_id)

        @property
        def status(self):
            return read_status

        @property
        def detail(self):
            return None

        def __setattr__(self, name, value):
            # What the model does: an unguarded write of whatever was decided.
            store.setdefault(doc_id, {})[name] = value

    return _Row()


def _walked(children=(), domains=()):
    walked = MagicMock()
    walked.domains = list(domains)
    walked.dependents.side_effect = lambda include_deleted=False: list(children)
    walked.domains_dependents.side_effect = lambda include_deleted=False: []
    return walked


def test_an_orphan_sweep_does_not_undelete_a_child_deleted_since_the_walk():
    """The child's own delete chain settled between the walk and the write."""
    from isardvdi_change_handler.task_results import storage

    store = {"c1": {"status": "deleted"}}
    # The child AS THE WALK READ IT, before its delete chain settled.
    walked = _walked(children=[_read_row(store, "c1", "ready")])

    with patch.object(storage, "Storage", _storage_over(store, walked)):
        storage._apply_storage_update({"id": "s1", "status": "orphan"})

    assert (
        store["c1"]["status"] == "deleted"
    ), f"a row a concurrent delete settled was un-deleted: {store['c1']}"


def test_an_orphan_sweep_still_orphans_a_child_that_is_still_there():
    """The control."""
    from isardvdi_change_handler.task_results import storage

    store = {"c1": {"status": "ready"}}
    walked = _walked(children=[_read_row(store, "c1", "ready")])

    with patch.object(storage, "Storage", _storage_over(store, walked)):
        storage._apply_storage_update({"id": "s1", "status": "orphan"})

    assert store["c1"]["status"] == "orphan"


def test_a_ready_storage_does_not_promote_a_domain_that_moved_since_the_read():
    """The domain left the waiting-on-storage set while the pass ran."""
    from isardvdi_change_handler.task_results import storage

    store = {"d1": {"status": "Started"}}
    walked = _walked(domains=[_read_row(store, "d1", "CreatingDomain")])

    with (
        patch.object(storage, "Storage", _storage_over(store, walked)),
        patch.object(storage, "Domain", _storage_over(store, walked)),
    ):
        storage._apply_storage_update({"id": "s1", "status": "ready"})

    assert (
        store["d1"]["status"] == "Started"
    ), f"a running domain was announced Stopped: {store['d1']}"
    assert "current_action" not in store["d1"]


def test_a_ready_storage_still_promotes_a_domain_that_is_still_waiting():
    """The control."""
    from isardvdi_change_handler.task_results import storage

    store = {"d1": {"status": "CreatingDomain"}}
    walked = _walked(domains=[_read_row(store, "d1", "CreatingDomain")])

    with (
        patch.object(storage, "Storage", _storage_over(store, walked)),
        patch.object(storage, "Domain", _storage_over(store, walked)),
    ):
        storage._apply_storage_update({"id": "s1", "status": "ready"})

    assert store["d1"]["status"] == "Stopped"
    assert store["d1"]["current_action"] is None
