# SPDX-License-Identifier: AGPL-3.0-or-later

"""The new-user quota/limit gate must be evaluated on every call.

``cachetools`` memoizes the return value and never the raised exception, so a
validator that signals "over quota" by raising and "ok" by returning is skipped
outright for the rest of the TTL once one call has returned. Keyed on
``(category_id, group_id)``, that let repeated creates into the same category
pass on the strength of the first one.

The gate reads the users count live, so these tests drive it down to the
RethinkDB boundary: ``_rdb_connection`` is a fake that answers only the exact
``r.table("users").get_all(<id>, index="group"|"category").count()`` query and
raises on anything else. A wrong table or a wrong index name therefore fails
here instead of reaching production as a 500 on user create.

``users`` and its ``group`` / ``category`` secondary indexes are the same ones
``process_group_limits`` / ``process_category_limits`` count with; the indexes
are declared in ``engine/engine/initdb/populate.py``.

``ErrorBase`` rather than ``error_factory.Error``: the factory resolves lazily
to either ``ErrorBase`` or apiv4's ``Error`` subclass depending on whether
``api.services.error`` is in ``sys.modules`` at first access, and it does not
cache the ``ErrorBase`` fallback, so importer and importee can disagree.
``ErrorBase`` matches both.
"""

import pytest
from isardvdi_common.helpers.error_base import ErrorBase
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.helpers.quotas_process import QuotasProcess
from rethinkdb import r

LIMIT = 2


class UnknownQuery(Exception):
    """Raised for a query the fake connection was not told to answer.

    Stands in for the ``ReqlOpFailedError`` RethinkDB returns when a query
    names an index the table does not have.
    """


class FakeRethinkConnection:
    """Answers registered count-by-index queries and nothing else.

    ``run()`` hands the driver connection the assembled ReQL term, so the
    production query is really built and compared against what was registered.
    """

    def __init__(self):
        self._routes = []
        self.served = []

    def count_by_index(self, table, index, key, count):
        """Answer ``r.table(table).get_all(key, index=index).count()``.

        ``count`` may be a callable so a test can move the number between
        calls, the way another create would.
        """
        route = (table, index, key)
        self._routes.append(
            (str(r.table(table).get_all(key, index=index).count()), route, count)
        )
        return self

    def _start(self, term, **global_optargs):
        query = str(term)
        for expected, route, count in self._routes:
            if query == expected:
                self.served.append(route)
                return count() if callable(count) else count
        raise UnknownQuery(query)


class NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _install_connection(monkeypatch, connection):
    monkeypatch.setattr(
        QuotasProcess, "_rdb_context", classmethod(lambda cls: NullContext())
    )
    monkeypatch.setattr(
        type(QuotasProcess), "_rdb_connection", property(lambda cls: connection)
    )
    return connection


def _limits_payload(kind, users):
    """The subset of a ``process_*_limits`` result that the gate reads."""
    return {
        kind: {"name": f"a-{kind}"},
        "u": users,
        "uq": LIMIT,
        "uqp": int(round(users * 100 / LIMIT, 0)),
    }


def _fake_backend(monkeypatch, counts, group_id, category_id):
    """Serve the gate stale limits and a live users count from ``counts``.

    ``process_*_limits`` is left stale on purpose (it is TTL-cached in
    production): only the users count follows ``counts``, which is exactly the
    number the decision compares.
    """
    stale = dict(counts)
    calls = {"group": 0, "category": 0}

    def process_group_limits(cls, id, from_user_id=None):
        calls["group"] += 1
        return _limits_payload("group", stale["group"])

    def process_category_limits(cls, id, from_user_id=None, from_group_id=None):
        calls["category"] += 1
        return _limits_payload("category", stale["category"])

    monkeypatch.setattr(
        QuotasProcess, "process_group_limits", classmethod(process_group_limits)
    )
    monkeypatch.setattr(
        QuotasProcess, "process_category_limits", classmethod(process_category_limits)
    )

    connection = FakeRethinkConnection()
    connection.count_by_index("users", "group", group_id, lambda: counts["group"])
    connection.count_by_index(
        "users", "category", category_id, lambda: counts["category"]
    )
    _install_connection(monkeypatch, connection)
    return calls, connection


def test_live_users_count_queries_the_users_table_by_index(monkeypatch):
    connection = _install_connection(
        monkeypatch,
        FakeRethinkConnection().count_by_index("users", "group", "grp-0", 7),
    )

    assert QuotasProcess._live_users_count("group", "grp-0") == 7
    assert connection.served == [("users", "group", "grp-0")]


def test_live_users_count_rejects_an_index_the_table_does_not_have(monkeypatch):
    _install_connection(
        monkeypatch,
        FakeRethinkConnection().count_by_index("users", "group", "grp-0", 7),
    )

    with pytest.raises(UnknownQuery):
        QuotasProcess._live_users_count("group_typo", "grp-0")


def test_user_create_gate_reevaluated_when_group_fills_up_inside_the_ttl(monkeypatch):
    counts = {"group": LIMIT - 1, "category": 0}
    calls, connection = _fake_backend(monkeypatch, counts, "grp-1", "cat-1")

    Quotas.UserCreate(category_id="cat-1", group_id="grp-1")

    # the user just created filled the group
    counts["group"] = LIMIT

    with pytest.raises(ErrorBase) as excinfo:
        Quotas.UserCreate(category_id="cat-1", group_id="grp-1")
    assert excinfo.value.error["description_code"] == "user_new_group_cuota_exceeded"
    assert calls["group"] == 2
    assert ("users", "group", "grp-1") in connection.served


def test_check_new_autoregistered_user_reevaluated_when_category_fills_up(monkeypatch):
    counts = {"group": 0, "category": LIMIT - 1}
    calls, connection = _fake_backend(monkeypatch, counts, "grp-2", "cat-2")

    QuotasProcess.check_new_autoregistered_user("cat-2", "grp-2")

    counts["category"] = LIMIT

    with pytest.raises(ErrorBase) as excinfo:
        QuotasProcess.check_new_autoregistered_user("cat-2", "grp-2")
    assert excinfo.value.error["description_code"] == "user_new_category_cuota_exceeded"
    assert calls["category"] == 2
    assert ("users", "category", "cat-2") in connection.served


def test_gate_keeps_passing_while_under_the_limit(monkeypatch):
    counts = {"group": 0, "category": 0}
    _fake_backend(monkeypatch, counts, "grp-3", "cat-3")

    for _ in range(3):
        assert Quotas.UserCreate(category_id="cat-3", group_id="grp-3") is None
