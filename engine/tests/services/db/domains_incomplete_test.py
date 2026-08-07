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

import importlib.util as _ilu
import sys as _sys
import types as _types
from unittest.mock import MagicMock as _MagicMock

from tests.helpers import ENGINE_SRC

# domains.py reads a real log level at import time (DEBUG_CHANGES). Set it on
# whatever ``logs`` already is instead of replacing the module: these test
# modules share one interpreter, and a fake ``engine.services.log`` left behind
# breaks the siblings that import the real names from it.
import engine.services.log as _engine_log

try:
    _engine_log.logs.changes.handlers[0].level = 20
except Exception:
    pass

# Load the module under test from its file with a stub parent package, so
# engine/services/db/__init__.py never runs (it star-imports siblings that
# connect at import time) and sys.modules is left as the conftest set it.
_saved = {
    _m: _sys.modules.get(_m)
    for _m in (
        "engine.services.db",
        "engine.services.db.db",
        "engine.services.db.domains",
        "rethinkdb",
    )
}
_pkg = _types.ModuleType("engine.services.db")
_pkg.__path__ = []
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
_sys.modules.pop("rethinkdb", None)

_spec = _ilu.spec_from_file_location(
    "engine.services.db.domains",
    str(ENGINE_SRC / "services" / "db" / "domains.py"),
)
mod = _ilu.module_from_spec(_spec)
_sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

for _m, _prev in _saved.items():
    if _prev is None:
        _sys.modules.pop(_m, None)
    else:
        _sys.modules[_m] = _prev

from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402


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
