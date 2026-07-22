"""Unit tests for the GPU planner manager-ownership guards.

``api_reservables_planner`` can't be imported bare (``from api import app`` boots
Flask + RethinkDB at import time), so — mirroring ``api_reservables_test.py`` — we
extract the two guard methods via ``ast`` and exec them with the module globals
they touch (``Error``, ``app``, ``r``, ``db``) replaced by stubs. This pins the
category-delegation authorization model:

- ``_assert_manager_owns_card``: admin passes; a manager passes only on a card
  whose ``gpus.category`` equals the manager's category (a global/None card is
  forbidden for a manager).
- ``_assert_manager_owns_plan``: a missing plan is ``not_found``; a cross-category
  plan's ``forbidden`` is COLLAPSED to ``not_found`` so a manager cannot
  enumerate other categories' plan ids by probing.
"""

import ast
import os

_SRC = os.path.join(os.path.dirname(__file__), "../reservables_planner.py")
_WANTED = {"_assert_manager_owns_card", "_assert_manager_owns_plan"}


class _Error(Exception):
    """Stand-in for isardvdi_common Error: first positional arg is the code, so
    ``e.args[0]`` matches the production ``raise Error("forbidden", ...)``. It
    also accepts the ``description_code=`` keyword the production raises pass."""

    _STATUS = {"forbidden": 403, "not_found": 404}

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.kwargs = kwargs
        # The twin's 403->404 collapse checks ``e.status_code`` (the
        # isardvdi_common error factory contract; ``e.args[0]`` is unreliable
        # there because Error stores a dict).
        self.status_code = self._STATUS.get(args[0] if args else None, 500)


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _App:
    def app_context(self):
        return _Ctx()


class _Table:
    def __init__(self, row):
        self._row = row

    def get(self, _id):
        return self

    def run(self, _conn):
        return self._row


class _R:
    def __init__(self, row):
        self._row = row

    def table(self, _name):
        return _Table(self._row)


class _DB:
    conn = None


def _load():
    tree = ast.parse(open(_SRC).read())
    funcs = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name in _WANTED
    ]
    assert {f.name for f in funcs} == _WANTED, "could not locate both guard methods"
    for f in funcs:
        # On this branch the guards are @classmethod-decorated; strip the
        # decorator so the exec'd functions bind as plain instance methods on
        # the _Self stand-in (cls/self both resolve to the harness object).
        f.decorator_list = []
    ns = {"Error": _Error, "app": _App(), "r": _R(None), "db": _DB()}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), _SRC, "exec"), ns)
    return ns


_H = _load()


class _Reservables:
    def __init__(self, category):
        self._category = category

    def get_item_category(self, _item_type, _item_id):
        return self._category


class _Self:
    """Minimal stand-in for the planner instance the guards are bound to."""

    def __init__(self, card_category):
        self.reservables = _Reservables(card_category)
        self._rdb_connection = None

    def _rdb_context(self):
        import contextlib

        return contextlib.nullcontext()

    _assert_manager_owns_card = _H["_assert_manager_owns_card"]
    _assert_manager_owns_plan = _H["_assert_manager_owns_plan"]


def _payload(role, category="catA"):
    return {"role_id": role, "category_id": category}


def _raises(fn):
    try:
        fn()
    except _Error as e:
        return e.args[0]
    return None  # no error raised


# --- _assert_manager_owns_card ----------------------------------------------


def test_admin_passes_any_card():
    s = _Self(card_category="catB")
    assert _raises(lambda: s._assert_manager_owns_card(_payload("admin"), "c")) is None


def test_manager_passes_own_category_card():
    s = _Self(card_category="catA")
    assert (
        _raises(lambda: s._assert_manager_owns_card(_payload("manager", "catA"), "c"))
        is None
    )


def test_manager_forbidden_on_other_category_card():
    s = _Self(card_category="catB")
    assert (
        _raises(lambda: s._assert_manager_owns_card(_payload("manager", "catA"), "c"))
        == "forbidden"
    )


def test_manager_forbidden_on_global_card():
    # A non-delegated (None) card is admin-only — forbidden for a manager.
    s = _Self(card_category=None)
    assert (
        _raises(lambda: s._assert_manager_owns_card(_payload("manager", "catA"), "c"))
        == "forbidden"
    )


# --- _assert_manager_owns_plan (403 -> 404 collapse) ------------------------


def _owns_plan(plan_row, card_category, payload):
    _H["r"] = _R(plan_row)  # the guard reads r.table(...).get(plan_id).run(...)
    s = _Self(card_category)
    return _raises(lambda: s._assert_manager_owns_plan(payload, "plan-id"))


def test_admin_passes_any_plan():
    assert _owns_plan({"item_id": "c"}, "catB", _payload("admin")) is None


def test_missing_plan_is_not_found():
    assert _owns_plan(None, "catA", _payload("manager", "catA")) == "not_found"


def test_cross_category_plan_collapses_403_to_404():
    # Manager probes a plan on a card delegated to ANOTHER category: the guard
    # must hide it as not_found, never leak a 403 that confirms it exists.
    assert (
        _owns_plan({"item_id": "c"}, "catB", _payload("manager", "catA")) == "not_found"
    )


def test_manager_own_category_plan_passes():
    assert _owns_plan({"item_id": "c"}, "catA", _payload("manager", "catA")) is None
