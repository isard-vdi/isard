#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Rollback in ``DesktopsProcessed.new_from_template`` when the disk-creation
chain refuses (#3391 / the rollback #4197 proposed).

``new_from_template`` inserts the domain row and then calls
``enqueue_disk_creation_chain_for_domain``. When that chain raises — most often
the ``428 storage_pending_task`` a reconcile tick provokes by racing the create —
the pre-fix code left the domain ``Creating`` and the storage parked, so the
desktop's name stayed taken and the user's retry got a 409. These pin the undo:
the domain row this call inserted is deleted so the name frees, the storage row
only if this call still owns it (unstarted, no task now on it — a task means
another actor is already settling it), and the original typed ``Error`` is
re-raised unchanged. The soft (deployment/bulk) path is covered too.

Every collaborator is stubbed; the insert/chain/rollback decision is taken by the
production code.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktops as mod

DP = mod.DesktopsProcessed


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ready_template():
    return {
        "id": "tmpl-1",
        "status": "Stopped",
        "description": "template description",
        "icon": "fa-desktop",
        "image": {"id": "img-1", "type": "stock"},
        "os": "linux",
        "hypervisors_pools": ["default"],
        "forced_hyp": False,
        "favourite_hyp": False,
        "parents": [],
        "create_dict": {"hardware": {"disks": [{"storage_id": "st-parent"}]}},
    }


def _user():
    return {"id": "u-1", "username": "bob", "category": "cat-1", "group": "grp-1"}


def _pending_task_error():
    return Error(
        "precondition_required",
        "Storage st-1 has the pending task find-1",
        description_code="storage_pending_task",
    )


@pytest.fixture
def env(monkeypatch):
    """Stub every collaborator so control reaches the insert/chain block, plus a
    ``Storage`` double whose re-read status and task ownership tests can tweak."""
    docs = {"domains": _ready_template(), "users": _user()}
    monkeypatch.setattr(
        mod.Caches,
        "get_document",
        classmethod(lambda cls, t, i, keys=None, invalidate=False: docs[t]),
    )
    monkeypatch.setattr(
        DP,
        "merge_new_data_with_template",
        classmethod(
            lambda cls, tid, nd: ({"hardware": {"interfaces": [], "memory": 2}}, {})
        ),
    )
    monkeypatch.setattr(
        mod.Helpers, "gen_interfaces_macs", classmethod(lambda cls, ifaces: ifaces)
    )
    monkeypatch.setattr(
        mod.Helpers, "_parse_media_info", classmethod(lambda cls, cd: cd)
    )
    monkeypatch.setattr(
        mod.Helpers, "gen_payload_from_user", classmethod(lambda cls, uid: {})
    )
    monkeypatch.setattr(
        mod.Helpers, "memory_gib_to_kib", staticmethod(lambda mem: 2048)
    )
    monkeypatch.setattr(
        mod.Quotas, "limit_user_hardware_allowed", staticmethod(lambda payload, cd: cd)
    )

    class _Schema:
        def __init__(self, **kw):
            self._kw = kw

        def model_dump(self, **k):
            return {**self._kw, "id": "dom-1"}

    monkeypatch.setattr(mod, "DesktopFromTemplate", _Schema)

    monkeypatch.setattr(DP, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(DP), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    monkeypatch.setattr(mod.r, "table", lambda name: MagicMock(name=f"r.table({name})"))

    pending = MagicMock(name="pending_storage")
    pending.id = "st-1"
    pending.path = "/isard/desktop/st-1.qcow2"
    fake_storage = MagicMock(name="Storage")
    fake_storage.new_dict.return_value = pending
    fake_storage.exists.return_value = True
    # Storage(sid) re-read in the rollback: unstarted by default.
    fake_storage.return_value = SimpleNamespace(status="maintenance")
    monkeypatch.setattr(mod, "Storage", fake_storage)

    monkeypatch.setattr(mod.Domain, "delete", MagicMock(name="Domain.delete"))

    import isardvdi_common.lib.task_index as tix
    import isardvdi_common.models.task as taskmod

    monkeypatch.setattr(tix, "current_task_id", MagicMock(return_value=None))
    fake_task = MagicMock(name="Task")
    fake_task._redis = MagicMock()
    fake_task.exists.return_value = True
    # Task(task_id).pending — a live (pending) task by default.
    fake_task.return_value = SimpleNamespace(pending=True)
    monkeypatch.setattr(taskmod, "Task", fake_task)

    return {
        "docs": docs,
        "pending": pending,
        "storage": fake_storage,
        "current_task_id": tix.current_task_id,
        "task": fake_task,
    }


def _create(env, name, **kw):
    return DP.new_from_template(name, "desc", "tmpl-1", "u-1", domain_id="dom-1", **kw)


class TestNewFromTemplateRollback:
    def test_chain_refusal_deletes_both_rows_and_reraises(self, env):
        env["pending"].enqueue_disk_creation_chain_for_domain.side_effect = (
            _pending_task_error()
        )
        with pytest.raises(Error) as exc:
            _create(env, "desk-a")
        assert exc.value.error["description_code"] == "storage_pending_task"
        mod.Domain.delete.assert_called_once_with("dom-1")
        env["storage"].delete.assert_called_once_with("st-1")

    def test_storage_with_a_live_task_is_left_for_that_task(self, env):
        # The race case: a reconcile find already owns the storage. Free the
        # name (delete the domain) but leave the storage for the find to settle.
        env["current_task_id"].return_value = "find-1"
        env["pending"].enqueue_disk_creation_chain_for_domain.side_effect = (
            _pending_task_error()
        )
        with pytest.raises(Error):
            _create(env, "desk-b")
        mod.Domain.delete.assert_called_once_with("dom-1")
        env["storage"].delete.assert_not_called()

    def test_storage_with_a_cancelled_task_is_still_deleted(self, env):
        # After fix A a park failure cancels the task; cancel keeps the rq hash so
        # current_task_id still names it, but a cancelled (non-pending) task must not strand the row.
        env["current_task_id"].return_value = "cancelled-1"
        env["task"].return_value = SimpleNamespace(pending=False)
        env["pending"].enqueue_disk_creation_chain_for_domain.side_effect = (
            _pending_task_error()
        )
        with pytest.raises(Error):
            _create(env, "desk-h")
        mod.Domain.delete.assert_called_once_with("dom-1")
        env["storage"].delete.assert_called_once_with("st-1")

    def test_storage_that_is_no_longer_unstarted_is_not_deleted(self, env):
        # A row that reached ready (a real disk) must never be deleted, even if
        # something after it raised.
        env["storage"].return_value = SimpleNamespace(status="ready")
        env["pending"].enqueue_disk_creation_chain_for_domain.side_effect = (
            _pending_task_error()
        )
        with pytest.raises(Error):
            _create(env, "desk-c")
        mod.Domain.delete.assert_called_once_with("dom-1")
        env["storage"].delete.assert_not_called()

    def test_success_path_inserts_and_does_not_roll_back(self, env):
        env["pending"].enqueue_disk_creation_chain_for_domain.return_value = "task-ok"
        result = _create(env, "desk-d")
        assert result["id"] == "dom-1"
        mod.Domain.delete.assert_not_called()
        env["storage"].delete.assert_not_called()

    def test_image_card_path_unchanged_on_success(self, env, monkeypatch):
        cards = MagicMock(name="Cards")
        monkeypatch.setattr(mod, "Cards", cards)
        env["pending"].enqueue_disk_creation_chain_for_domain.return_value = "task-ok"
        _create(env, "desk-e", image={"id": "img-9", "type": "user"})
        cards.update.assert_called_once_with("dom-1", "img-9", "user")
        mod.Domain.delete.assert_not_called()

    def test_chain_refusal_rolls_back_before_touching_cards(self, env, monkeypatch):
        cards = MagicMock(name="Cards")
        monkeypatch.setattr(mod, "Cards", cards)
        env["pending"].enqueue_disk_creation_chain_for_domain.side_effect = (
            _pending_task_error()
        )
        with pytest.raises(Error):
            _create(env, "desk-f", image={"id": "img-9", "type": "user"})
        cards.update.assert_not_called()
        cards.upload.assert_not_called()

    def test_soft_deployment_path_rolls_back_on_refusal(self, env):
        env["pending"].enqueue_disk_creation_chain_for_domain.side_effect = (
            _pending_task_error()
        )
        with pytest.raises(Error) as exc:
            _create(env, "desk-g", soft=True)
        assert exc.value.error["description_code"] == "storage_pending_task"
        mod.Domain.delete.assert_called_once_with("dom-1")
        env["storage"].delete.assert_called_once_with("st-1")
