# SPDX-License-Identifier: AGPL-3.0-or-later

"""The DataTables filters of the logs query, checked on the real ReQL term it builds."""

import re
from contextlib import nullcontext

import pytest
from isardvdi_common.lib.logs.logs import LogsProcessed
from rethinkdb import ast


def _terms(term, kind):
    if isinstance(term, kind):
        yield term
    for arg in getattr(term, "_args", []):
        yield from _terms(arg, kind)
    for arg in getattr(term, "optargs", {}).values():
        yield from _terms(arg, kind)


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    monkeypatch.setattr(LogsProcessed, "_rdb_context", lambda: nullcontext())
    monkeypatch.setattr(ast.RqlQuery, "run", lambda self, *a, **kw: [])


def _query(parsed):
    query, _ = LogsProcessed._build_query("logs_desktops", parsed, ordered=False)
    return query


def _column_search(field, value):
    return {"columns": [{"data": field, "search": {"value": value}}]}


@pytest.mark.parametrize(
    "parsed",
    [
        {"filter_field": "desktop_id", "filter_value": "d1"},
        _column_search("owner_user_name", "bob"),
        {
            "filter_field": "user_id",
            "filter_value": "u1",
            "columns": {"0": {"data": "request_ip", "search": {"value": "10."}}},
        },
    ],
)
def test_every_filter_function_takes_one_argument(parsed):
    funcs = list(_terms(_query(parsed), ast.Func))

    assert funcs
    assert [len(f._args[0]._args) for f in funcs] == [1] * len(funcs)


@pytest.mark.parametrize("value", ["a.b", "(a+)+$", "^admin", "[a-z]+"])
def test_the_column_search_value_reaches_match_as_a_literal(value):
    matches = list(_terms(_query(_column_search("owner_user_name", value)), ast.Match))

    assert [getattr(m._args[1], "data", None) for m in matches] == [re.escape(value)]


@pytest.mark.parametrize("field", ["name'] or 1", "a[0]", "with space", "$where"])
def test_a_column_name_that_is_not_a_field_path_adds_no_filter(field):
    query = _query(_column_search(field, "x"))

    assert not list(_terms(query, ast.Filter))


def test_a_filter_field_that_is_not_a_field_path_adds_no_filter():
    query = _query({"filter_field": "user_id['x']", "filter_value": "u1"})

    assert not list(_terms(query, ast.Filter))
