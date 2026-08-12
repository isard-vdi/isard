"""Unit tests for the incomplete-``Creating``-domain sweep's protection gate.

Same import harness as ``hypervisors_filters_test.py`` (see its header): the
package is stubbed so the module loads without ``engine.services.db.db``, which
connects to RethinkDB at import time.

What is pinned here is which storages protect their domain from the sweep. The
sweep deletes a domain stuck in a ``Creating*`` status; a storage with disk
creation IN FLIGHT must stop it, or the delete orphans the storage row and the
qcow2 the chain is still writing.

The gate takes a STORAGE id and asks the task index what that row is busy with,
so ``_index`` here stands for the index's answer.
"""

import os as _os
import sys as _sys
import types as _types
from unittest.mock import MagicMock as _MagicMock

_pkg = _types.ModuleType("engine.services.db")
_pkg.__path__ = [_os.path.dirname(_os.path.abspath(__file__))]
for _name in (
    "close_rethink_connection",
    "create_list_buffer_history_domain",
    "new_rethink_connection",
    "rethink_conn",
):
    setattr(_pkg, _name, _MagicMock())
_sys.modules["engine.services.db"] = _pkg
# domains.py also imports engine.services.db.db, which connects at import time.
_db = _types.ModuleType("engine.services.db.db")
_db.close_rethink_connection = _MagicMock()
_db.new_rethink_connection = _MagicMock()
_sys.modules["engine.services.db.db"] = _db
# domains.py reads a real log level at import time (DEBUG_CHANGES). Set it on
# whatever ``logs`` already is instead of replacing the module: these test
# modules share one interpreter, and a fake ``engine.services.log`` left behind
# breaks the siblings that import the real names from it.
import engine.services.log as _engine_log  # noqa: E402

try:
    _engine_log.logs.changes.handlers[0].level = 20
except Exception:
    pass
_sys.modules.pop("engine.services.db.domains", None)
_sys.modules.pop("rethinkdb", None)

from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402

import engine.services.db.domains as mod  # noqa: E402

# The module is loaded; drop the stubs again so the sibling test modules — which
# share this interpreter and build their own — are not handed ours. Collection
# order is alphabetical, so anything left here lands on them.
for _stub in ("engine.services.db.db", "engine.services.db"):
    _sys.modules.pop(_stub, None)


class _Task:
    """Stand-in for the Task model: a registry of id -> pending, where an id
    that is absent is a job rq no longer has."""

    registry = {}
    # the gate hands the index the shared connection off the model
    _redis = None

    def __init__(self, task_id):
        self.id = task_id

    @classmethod
    def exists(cls, task_id):
        return task_id in cls.registry

    @property
    def pending(self):
        return cls_pending(self.id)


def cls_pending(task_id):
    return _Task.registry[task_id]


@pytest.fixture(autouse=True)
def _registry():
    _Task.registry = {}
    yield
    _Task.registry = {}


def _in_flight(task_id, storage_id="disk-1"):
    """Run the gate with the index answering ``task_id`` for ``storage_id``."""
    index = _types.SimpleNamespace(current_task_id=lambda conn, owner, **kw: task_id)
    with patch.dict(
        _sys.modules,
        {
            "isardvdi_common.models.task": _types.SimpleNamespace(Task=_Task),
            "isardvdi_common.lib.task_index": index,
        },
    ):
        return mod._storage_task_in_flight(storage_id)


class TestWhatProtectsADomainFromTheSweep:
    def test_a_running_task_protects(self):
        _Task.registry["t-1"] = True
        assert _in_flight("t-1") is True

    def test_a_settled_task_does_not_protect(self):
        """The chain finished or failed; the domain is genuinely incomplete and
        the sweep is what cleans it up."""
        _Task.registry["t-1"] = False
        assert _in_flight("t-1") is False

    def test_a_task_whose_job_is_gone_does_not_protect(self):
        """The case that made the old gate protect forever. Nothing in the
        stack ever clears the row's task field, so a pointer outlives its job
        indefinitely and its domain could never be swept."""
        assert _in_flight("expired-long-ago") is False

    def test_a_row_the_index_calls_free_does_not_protect(self):
        assert _in_flight(None) is False

    def test_no_storage_at_all_does_not_protect(self):
        assert _in_flight("t-1", storage_id=None) is False

    def test_a_row_with_no_task_does_not_protect(self):
        assert _in_flight(None) is False
        assert _in_flight("") is False

    def test_an_unreadable_task_protects(self):
        """Fail SAFE. This gate stands in front of a delete: uncertainty must
        keep the domain, never remove it."""

        class _Boom(_Task):
            @classmethod
            def exists(cls, task_id):
                raise RuntimeError("redis unreachable")

        index = _types.SimpleNamespace(current_task_id=lambda conn, owner, **kw: "t-1")
        with patch.dict(
            _sys.modules,
            {
                "isardvdi_common.models.task": _types.SimpleNamespace(Task=_Boom),
                "isardvdi_common.lib.task_index": index,
            },
        ):
            assert mod._storage_task_in_flight("disk-1") is True

        with patch.dict(
            _sys.modules,
            {"isardvdi_common.models.task": _types.SimpleNamespace(Task=_Boom)},
        ):
            assert mod._storage_task_in_flight("t-1") is True
