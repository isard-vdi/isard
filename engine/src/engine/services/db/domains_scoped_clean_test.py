"""``clean_intermediate_status(only_domain_id=X)`` must touch X and nothing else.

Same import harness as ``domains_incomplete_test.py`` (see its header).

The three sweeps behave as a set: each takes an optional ``only_domain_id`` and
must run EITHER the one-domain query on the ``id`` index OR the fleet-wide one
on the ``status`` index. ``move_actions_to_others_hypers`` calls the scoped form
once per queued action of a hypervisor that lost its worker, so a sweep that
runs the fleet-wide query anyway rewrites every in-flight domain in the
installation, once per action.

The queries here are recorded rather than executed: what is pinned is which
index each call reaches for, which is exactly what went wrong.
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
_db = _types.ModuleType("engine.services.db.db")
_db.close_rethink_connection = _MagicMock()
_db.new_rethink_connection = _MagicMock()
_sys.modules["engine.services.db.db"] = _db
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

for _stub in ("engine.services.db.db", "engine.services.db"):
    _sys.modules.pop(_stub, None)


class _Args(list):
    """What ``r.args(...)`` returns: a marker carrying the status list."""


class _Query:
    """Records the chain built on it; ``run`` files it with the recorder."""

    def __init__(self, recorder, steps=()):
        self._recorder = recorder
        self.steps = list(steps)

    def _then(self, name, *args, **kwargs):
        return _Query(self._recorder, self.steps + [(name, args, kwargs)])

    def get_all(self, *a, **kw):
        return self._then("get_all", *a, **kw)

    def filter(self, *a, **kw):
        return self._then("filter", *a, **kw)

    def update(self, *a, **kw):
        return self._then("update", *a, **kw)

    def replace(self, *a, **kw):
        return self._then("replace", *a, **kw)

    def run(self, conn):
        self._recorder.append(self.steps)
        return {"replaced": 1, "errors": 0}


class _R:
    def __init__(self, recorder):
        self._recorder = recorder

    def table(self, name):
        return _Query(self._recorder)

    @staticmethod
    def args(values):
        return _Args(values)

    @staticmethod
    def expr(values):
        return _types.SimpleNamespace(contains=lambda _field: True)


@pytest.fixture
def ran():
    """Run the sweeps against a recorder instead of a database."""
    recorder = []
    with patch.object(mod, "r", _R(recorder)), patch.object(
        mod, "new_rethink_connection", _MagicMock()
    ), patch.object(mod, "close_rethink_connection", _MagicMock()):
        yield recorder


def _indexes(queries):
    return [
        kwargs.get("index")
        for query in queries
        for name, _args, kwargs in query
        if name == "get_all"
    ]


def _targets(queries):
    return [
        args[0] for query in queries for name, args, _kw in query if name == "get_all"
    ]


SWEEPS = pytest.mark.parametrize(
    "sweep",
    [
        mod.fail_incomplete_creating_domains,
        mod.stop_incomplete_starting_domains,
        mod.start_incomplete_starting_domains,
    ],
    ids=["fail_creating", "stop_starting", "start_stopping"],
)


@SWEEPS
def test_a_scoped_sweep_runs_only_the_one_domain_query(ran, sweep):
    sweep(only_domain_id="d-1")

    assert len(ran) == 1
    assert _indexes(ran) == ["id"]
    assert _targets(ran) == ["d-1"]


@SWEEPS
def test_an_unscoped_sweep_runs_only_the_fleet_wide_query(ran, sweep):
    sweep(only_domain_id=None)

    assert len(ran) == 1
    assert _indexes(ran) == ["status"]
    assert isinstance(_targets(ran)[0], _Args)


class _EmptyQuery(_Query):
    """Same recorder, but ``run`` answers with an empty result set.

    ``delete_incomplete_creating_domains`` — the fourth sweep, the one the
    parametrization above cannot take because it reads rows instead of updating
    them — wraps its scoped read in ``list()`` and then walks the rows. The dict
    ``_Query.run`` returns would be read as a list of key strings and blow up on
    ``.get``. No row is needed here: what is pinned is the index each query
    reached for.
    """

    def _then(self, name, *args, **kwargs):
        return _EmptyQuery(self._recorder, self.steps + [(name, args, kwargs)])

    def delete(self, *a, **kw):
        return self._then("delete", *a, **kw)

    def pluck(self, *a, **kw):
        return self._then("pluck", *a, **kw)

    def run(self, conn):
        self._recorder.append(self.steps)
        return []


class _EmptyR(_R):
    def table(self, name):
        return _EmptyQuery(self._recorder)


@pytest.fixture
def ran_rows():
    recorder = []
    with patch.object(mod, "r", _EmptyR(recorder)), patch.object(
        mod, "new_rethink_connection", _MagicMock()
    ), patch.object(mod, "close_rethink_connection", _MagicMock()):
        yield recorder


def test_the_fourth_sweep_is_scoped_too(ran_rows):
    """``delete_incomplete_creating_domains`` is the sweep the parametrization
    above cannot take, and the only one that DELETES rows rather than
    restamping them — so it is the one where a lost ``else`` costs the most.

    ``clean_intermediate_status`` runs it first, on the same
    ``only_domain_id``, which is why it belongs to the same set. It has its
    ``else`` today; this pins it, since the regression it guards against is
    exactly the one its neighbour suffered.
    """
    mod.delete_incomplete_creating_domains(only_domain_id="d-1")

    assert _indexes(ran_rows) == ["id"]
    assert _targets(ran_rows) == ["d-1"]


def test_the_fourth_sweep_unscoped_is_fleet_wide(ran_rows):
    mod.delete_incomplete_creating_domains(only_domain_id=None)

    assert _indexes(ran_rows) == ["status"]
    assert isinstance(_targets(ran_rows)[0], _Args)


def test_the_scoped_sweep_never_reaches_the_status_index(ran):
    """The regression itself, stated as the caller experiences it.

    ``fail_incomplete_creating_domains`` had no ``else``, so a call meant for
    one domain also ran the fleet-wide update over ``Updating``, ``Deleting``,
    ``DiskDeleted``, ``CreatingDomain``, ``DeletingDomainDisk`` and
    ``StartingDomainDisposable`` — every in-flight creation in the install went
    to ``Failed`` because one hypervisor lost its worker thread.
    """
    mod.fail_incomplete_creating_domains(only_domain_id="d-1")

    assert "status" not in _indexes(ran)
