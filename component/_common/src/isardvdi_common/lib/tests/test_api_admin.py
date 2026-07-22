#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ApiAdmin generic-table CRUD methods.

These three methods (insert/update/delete) replaced the inline
rethinkdb queries in ``apiv4/api/services/admin/tables.py`` as
the Tier 3.4 Batch 0 "shape" PR — establishing the convention
for the next ~25 query migrations.

We don't talk to a real RethinkDB. Each test stubs ``r.table``
and the connection at module-scope so the method's branching
logic is exercised against the contract documented in the
docstrings. The tests pin:

* insert: ``conflict`` when id exists, ``internal_server`` when
  rdb returns ``inserted == 0``, success otherwise.
* update: silent no-op (rethinkdb's get(id).update is forgiving
  and the method delegates with no checks).
* delete: ``not_found`` when row is missing, ``internal_server``
  on ``deleted == 0``.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    """Stub the rdb connection + validate_table on ApiAdmin.

    Yields a dict with ``mock_table`` (chained MagicMock for
    r.table(...)) so each test can wire up the .get / .insert /
    .update / .delete / .run return values.
    """
    from isardvdi_common.lib import api_admin as mod

    monkeypatch.setattr(
        mod.ApiAdmin, "_validate_table", classmethod(lambda cls, t: None)
    )

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.ApiAdmin, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(mod.ApiAdmin),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "ApiAdmin": mod.ApiAdmin}


# ---- insert_table_item -------------------------------------------------


class TestInsertTableItem:
    def test_conflict_when_id_exists(self, stub_rdb):
        """Existing row → Error('conflict')."""
        from isardvdi_common.helpers.error_factory import Error

        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = {
            "id": "x"
        }
        with pytest.raises(Error) as exc:
            stub_rdb["ApiAdmin"].insert_table_item(
                "interfaces", {"id": "x", "name": "n"}
            )
        assert exc.value.error.get("error") == "conflict"

    def test_success_when_id_free(self, stub_rdb):
        """Missing row + inserted=1 → no exception."""
        # First .run() returns None (existence check),
        # second .run() returns {"inserted": 1} (insert result).
        run = MagicMock(side_effect=[None, {"inserted": 1}])
        stub_rdb["mock_table"].return_value.get.return_value.run = run
        stub_rdb["mock_table"].return_value.insert.return_value.run = run
        stub_rdb["ApiAdmin"].insert_table_item("interfaces", {"id": "x", "name": "n"})

    def test_internal_server_on_inserted_zero(self, stub_rdb):
        """Missing row + inserted=0 → Error('internal_server')."""
        from isardvdi_common.helpers.error_factory import Error

        run = MagicMock(side_effect=[None, {"inserted": 0}])
        stub_rdb["mock_table"].return_value.get.return_value.run = run
        stub_rdb["mock_table"].return_value.insert.return_value.run = run
        with pytest.raises(Error) as exc:
            stub_rdb["ApiAdmin"].insert_table_item(
                "interfaces", {"id": "x", "name": "n"}
            )
        assert exc.value.error.get("error") == "internal_server"


# ---- update_table_item -------------------------------------------------


class TestUpdateTableItem:
    def test_delegates_to_get_id_update(self, stub_rdb):
        """update_table_item calls r.table(t).get(id).update(data).run(...)."""
        stub_rdb["ApiAdmin"].update_table_item(
            "interfaces", {"id": "x", "name": "renamed"}
        )
        stub_rdb["mock_table"].assert_any_call("interfaces")
        stub_rdb["mock_table"].return_value.get.assert_any_call("x")


# ---- delete_table_item -------------------------------------------------


class TestDeleteTableItem:
    def test_not_found_when_row_missing(self, stub_rdb):
        """get(id).run returns None → Error('not_found')."""
        from isardvdi_common.helpers.error_factory import Error

        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = None
        with pytest.raises(Error) as exc:
            stub_rdb["ApiAdmin"].delete_table_item("interfaces", "x")
        assert exc.value.error.get("error") == "not_found"

    def test_success_when_deleted(self, stub_rdb):
        """get(id) returns row → delete called → deleted=1 → no exception."""
        run = MagicMock(side_effect=[{"id": "x"}, {"deleted": 1}])
        stub_rdb["mock_table"].return_value.get.return_value.run = run
        stub_rdb["mock_table"].return_value.get.return_value.delete.return_value.run = (
            run
        )
        stub_rdb["ApiAdmin"].delete_table_item("interfaces", "x")

    def test_internal_server_on_deleted_zero(self, stub_rdb):
        """deleted=0 from rdb → Error('internal_server')."""
        from isardvdi_common.helpers.error_factory import Error

        run = MagicMock(side_effect=[{"id": "x"}, {"deleted": 0}])
        stub_rdb["mock_table"].return_value.get.return_value.run = run
        stub_rdb["mock_table"].return_value.get.return_value.delete.return_value.run = (
            run
        )
        with pytest.raises(Error) as exc:
            stub_rdb["ApiAdmin"].delete_table_item("interfaces", "x")
        assert exc.value.error.get("error") == "internal_server"


# ---- system_tables() process-wide cache --------------------------------


class TestSystemTablesCache:
    """Pin the process-wide cache for ``ApiAdmin.system_tables()``.

    Surfaced as a hot path by the rev-13 slow-query attribution: the
    method fired 90× in 21 s on admin-table scenarios because every
    ``_validate_table`` call re-queries ``r.table_list()``. Caching
    the result drops the rdb round-trip count to one per process.
    """

    @pytest.fixture
    def stub_pool_table_list(self, monkeypatch):
        """Stub ``_rdb_context`` + ``r.table_list().run(...)`` and
        clear the process-wide cache so each test starts fresh."""
        from isardvdi_common.lib import api_admin as mod

        mod.ApiAdmin.clear_system_tables_cache()

        class _Ctx:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(
            mod.ApiAdmin, "_rdb_context", classmethod(lambda cls: _Ctx())
        )
        monkeypatch.setattr(
            type(mod.ApiAdmin),
            "_rdb_connection",
            property(lambda self: MagicMock(name="conn")),
        )

        run = MagicMock(return_value=["users", "domains", "config"])
        table_list = MagicMock()
        table_list.run = run
        monkeypatch.setattr(mod.r, "table_list", lambda: table_list)
        yield {"run": run, "ApiAdmin": mod.ApiAdmin, "mod": mod}
        mod.ApiAdmin.clear_system_tables_cache()

    def test_first_call_hits_rdb(self, stub_pool_table_list):
        """Cold cache: first call must read rdb."""
        ApiAdmin = stub_pool_table_list["ApiAdmin"]
        result = ApiAdmin.system_tables()
        assert result == ["users", "domains", "config"]
        assert stub_pool_table_list["run"].call_count == 1

    def test_repeated_calls_reuse_cache(self, stub_pool_table_list):
        """Warm cache: every subsequent call must skip rdb. This is
        the whole point — 90 calls / 21 s drops to 1."""
        ApiAdmin = stub_pool_table_list["ApiAdmin"]
        ApiAdmin.system_tables()
        ApiAdmin.system_tables()
        ApiAdmin.system_tables()
        assert stub_pool_table_list["run"].call_count == 1, (
            "system_tables() must hit rdb only on the first call; "
            "see Bug 38/rev-13 attribution"
        )

    def test_clear_cache_re_reads(self, stub_pool_table_list):
        """The explicit invalidator must drop the cache so the next
        call re-reads. Production rarely uses this, but tests rely on
        it for isolation between cases."""
        ApiAdmin = stub_pool_table_list["ApiAdmin"]

        ApiAdmin.system_tables()
        assert stub_pool_table_list["run"].call_count == 1

        ApiAdmin.clear_system_tables_cache()
        ApiAdmin.system_tables()
        assert stub_pool_table_list["run"].call_count == 2

    def test_validate_table_uses_cache(self, stub_pool_table_list):
        """Pin the actual hot caller: ``_validate_table`` must NOT
        re-query rdb on every call. This is what made the system
        slow under load."""
        ApiAdmin = stub_pool_table_list["ApiAdmin"]

        for _ in range(50):
            ApiAdmin._validate_table("users")

        assert stub_pool_table_list["run"].call_count == 1, (
            "_validate_table must reuse the cached table list; if it "
            "re-queries every time the rev-13 perf regression returns"
        )
