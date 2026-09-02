#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``RethinkBase.exists()`` resolves a missing row instead of raising.

``r.table(t).get(id)["id"]`` raises ReqlNonExistenceError when the row is
gone, and the pooled-connection observer logs every raising query as
``rdb_query_failed`` — even when the caller expects the absence. The
bracket must carry ``.default(False)`` so the absent case is a value, not
an error.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.connections import rethink_base as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Doc(mod.RethinkBase):
        _rdb_table = "domains"
        _rdb_connection = MagicMock(name="conn")

    monkeypatch.setattr(Doc, "_rdb_context", classmethod(lambda cls: _Ctx()))
    table = MagicMock(name="table-domains")
    monkeypatch.setattr(mod.r, "table", MagicMock(return_value=table))
    return {"Cls": Doc, "table": table}


def _bracket(stub):
    # r.table("domains").get(id)["id"].default(False)
    return stub["table"].get.return_value.__getitem__.return_value


def test_missing_document_returns_false_without_raising(stub_rdb):
    _bracket(stub_rdb).default.return_value.run.return_value = False
    assert stub_rdb["Cls"].exists("gone") is False
    _bracket(stub_rdb).default.assert_called_once_with(False)


def test_present_document_returns_true(stub_rdb):
    _bracket(stub_rdb).default.return_value.run.return_value = "d-1"
    assert stub_rdb["Cls"].exists("d-1") is True


def test_other_errors_still_propagate(stub_rdb):
    _bracket(stub_rdb).default.return_value.run.side_effect = RuntimeError("no conn")
    with pytest.raises(RuntimeError):
        stub_rdb["Cls"].exists("d-1")
