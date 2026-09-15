#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``UsersAuthenticationProcessed`` (tier 3.4 batch 2).

Migrated from the inline rethink hits previously living in apiv4's
``services/admin/authentication.py``. Validation, authz, and
disclaimer-payload sanitisation stay in apiv4 — these tests pin the
data-access contract.
"""

import contextlib
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.users.users import authentication as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.UsersAuthenticationProcessed,
        "_rdb_context",
        classmethod(lambda cls: _Ctx()),
    )
    monkeypatch.setattr(
        type(mod.UsersAuthenticationProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    monkeypatch.setattr(mod.r, "now", lambda: "FAKE_NOW")
    monkeypatch.setattr(mod.r, "branch", lambda *a: ("BRANCH", a))

    yield {"mock_table": mock_table, "Processed": mod.UsersAuthenticationProcessed}


# ── Policies ──────────────────────────────────────────────────────────────


class TestInsertPolicy:
    def test_dispatches_insert(self, stub_rdb):
        stub_rdb["Processed"].insert_policy({"category": "all"})
        stub_rdb["mock_table"].assert_any_call("authentication")
        stub_rdb["mock_table"].return_value.insert.assert_called_with(
            {"category": "all"}
        )


class TestGetPolicy:
    def test_returns_row_when_present(self, stub_rdb):
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = {
            "id": "p1"
        }
        assert stub_rdb["Processed"].get_policy("p1") == {"id": "p1"}

    def test_raises_not_found_when_missing(self, stub_rdb):
        from isardvdi_common.helpers.error_base import ErrorBase

        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = None
        with pytest.raises(ErrorBase) as exc:
            stub_rdb["Processed"].get_policy("missing")
        assert exc.value.error.get("error") == "not_found"
        assert exc.value.error.get("description_code") == "auth_policy_not_found"


class TestUpdateDeletePolicy:
    def test_update_dispatches(self, stub_rdb):
        stub_rdb["Processed"].update_policy("p1", {"role": "manager"})
        stub_rdb["mock_table"].return_value.get.assert_called_with("p1")
        stub_rdb["mock_table"].return_value.get.return_value.update.assert_called_with(
            {"role": "manager"}
        )

    def test_delete_dispatches(self, stub_rdb):
        stub_rdb["Processed"].delete_policy("p1")
        stub_rdb["mock_table"].return_value.get.assert_called_with("p1")
        stub_rdb["mock_table"].return_value.get.return_value.delete.assert_called_once()


class TestHasDuplicatePolicy:
    def test_true_when_row_exists(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.filter.return_value.run.return_value = [
            {"id": "existing"}
        ]
        assert (
            stub_rdb["Processed"].has_duplicate_policy("cat", "role", "local") is True
        )

    def test_false_when_no_row(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.filter.return_value.run.return_value = []
        assert (
            stub_rdb["Processed"].has_duplicate_policy("cat", "role", "local") is False
        )


# ── Cache invalidation ───────────────────────────────────────────────────


@pytest.fixture
def stub_policies(stub_rdb, monkeypatch):
    from isardvdi_common.lib.users.users import user_policies as policies_mod

    monkeypatch.setattr(
        policies_mod.UserPolicies,
        "_rdb_context",
        classmethod(lambda cls: contextlib.nullcontext()),
    )
    policies_mod.UserPolicies.get_policies_category_role_provider.cache_clear()
    policies_mod.UserPolicies.get_user_policy.cache_clear()
    stub_rdb["mock_table"].return_value.filter.return_value.run.return_value = [
        {"category": "all", "role": "all", "disclaimer": True}
    ]
    yield {**stub_rdb, "UserPolicies": policies_mod.UserPolicies}
    policies_mod.UserPolicies.get_policies_category_role_provider.cache_clear()
    policies_mod.UserPolicies.get_user_policy.cache_clear()


WRITERS = [
    pytest.param(lambda p: p.insert_policy({"category": "all"}), id="insert_policy"),
    pytest.param(
        lambda p: p.update_policy("p1", {"disclaimer": False}), id="update_policy"
    ),
    pytest.param(lambda p: p.delete_policy("p1"), id="delete_policy"),
]


class TestPolicyWritersInvalidateUserPoliciesCaches:
    @pytest.mark.parametrize("write", WRITERS)
    def test_policies_category_role_provider_hits_db_again(self, stub_policies, write):
        run = stub_policies["mock_table"].return_value.filter.return_value.run
        policies = stub_policies["UserPolicies"]
        policies.get_policies_category_role_provider("cat-1", "user", "local")
        write(stub_policies["Processed"])
        policies.get_policies_category_role_provider("cat-1", "user", "local")
        assert run.call_count == 2

    @pytest.mark.parametrize("write", WRITERS)
    def test_user_policy_hits_db_again(self, stub_policies, write):
        run = stub_policies["mock_table"].return_value.filter.return_value.run
        policies = stub_policies["UserPolicies"]
        policies.get_user_policy("disclaimer", "cat-1", "user", "local")
        write(stub_policies["Processed"])
        policies.get_user_policy("disclaimer", "cat-1", "user", "local")
        assert run.call_count == 2


@pytest.fixture
def stub_caches(stub_rdb, monkeypatch):
    from isardvdi_common.helpers.caches import Caches

    monkeypatch.setattr(
        Caches,
        "_rdb_context",
        classmethod(lambda cls: contextlib.nullcontext()),
    )
    Caches.get_cached_users_migrations_exceptions.cache_clear()
    stub_rdb["mock_table"].return_value.run.return_value = []
    yield {**stub_rdb, "Caches": Caches}
    Caches.get_cached_users_migrations_exceptions.cache_clear()


MIGRATION_EXCEPTION_WRITERS = [
    pytest.param(
        lambda p: p.insert_migration_exceptions("users", ["u1"]),
        id="insert_migration_exceptions",
    ),
    pytest.param(
        lambda p: p.delete_migration_exception("ex-1"),
        id="delete_migration_exception",
    ),
]


class TestMigrationExceptionWritersInvalidateCachesCache:
    @pytest.mark.parametrize("write", MIGRATION_EXCEPTION_WRITERS)
    def test_users_migrations_exceptions_hits_db_again(self, stub_caches, write):
        run = stub_caches["mock_table"].return_value.run
        caches = stub_caches["Caches"]
        caches.get_cached_users_migrations_exceptions()
        write(stub_caches["Processed"])
        caches.get_cached_users_migrations_exceptions()
        assert run.call_count == 2


# ── Force policy at login ────────────────────────────────────────────────


class TestForcePolicyAtLogin:
    def test_filters_by_category_and_role(self, stub_rdb):
        chain = stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.filter.return_value.filter.return_value
        stub_rdb["Processed"].force_policy_at_login(
            {"type": "saml", "category": "cat-1", "role": "manager"},
            "disclaimer_acknowledged",
        )
        chain.update.assert_called_with({"disclaimer_acknowledged": None})
        # users table only — provider index lookup
        stub_rdb["mock_table"].assert_any_call("users")
        stub_rdb["mock_table"].return_value.get_all.assert_called_with(
            "saml", index="provider"
        )

    def test_skips_filters_when_all(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value.get_all.return_value
        stub_rdb["Processed"].force_policy_at_login(
            {"type": "local", "category": "all", "role": "all"}, "policy_field"
        )
        chain.update.assert_called_with({"policy_field": None})


# ── Disclaimer ───────────────────────────────────────────────────────────


class TestGetUserDisclaimerFields:
    def test_plucks_fields(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.return_value = {
            "role": "user",
            "lang": "en",
            "provider": "local",
        }
        assert stub_rdb["Processed"].get_user_disclaimer_fields("u1") == {
            "role": "user",
            "lang": "en",
            "provider": "local",
        }
        stub_rdb["mock_table"].return_value.get.return_value.pluck.assert_called_with(
            "role", "lang", "provider"
        )


class TestGetNotificationTemplate:
    def test_returns_row(self, stub_rdb):
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = {
            "id": "tpl-1",
            "lang": {},
        }
        assert stub_rdb["Processed"].get_notification_template("tpl-1") == {
            "id": "tpl-1",
            "lang": {},
        }


# ── Migration exceptions ─────────────────────────────────────────────────


class TestListMigrationExceptionsWithItemName:
    def test_returns_merged_rows(self, stub_rdb):
        rows = [{"id": "ex-1", "item_id": "user-1", "item_name": "alice"}]
        stub_rdb["mock_table"].return_value.merge.return_value.run.return_value = rows
        assert stub_rdb["Processed"].list_migration_exceptions_with_item_name() == rows
        stub_rdb["mock_table"].assert_any_call("users_migrations_exceptions")


class TestGetExistingMigrationExceptionIds:
    def test_returns_set_of_ids(self, stub_rdb):
        chain = stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.__getitem__.return_value
        chain.run.return_value = ["a", "b"]
        result = stub_rdb["Processed"].get_existing_migration_exception_ids(
            ["a", "b", "c"]
        )
        assert result == {"a", "b"}
        stub_rdb["mock_table"].return_value.get_all.assert_called_with(
            "a", "b", "c", index="item_id"
        )

    def test_empty_input_returns_empty_set(self, stub_rdb):
        assert stub_rdb["Processed"].get_existing_migration_exception_ids([]) == set()


class TestInsertMigrationExceptions:
    def test_skips_when_empty(self, stub_rdb):
        stub_rdb["Processed"].insert_migration_exceptions("users", [])
        stub_rdb["mock_table"].return_value.insert.assert_not_called()

    def test_dispatches_insert(self, stub_rdb):
        stub_rdb["Processed"].insert_migration_exceptions("users", ["a", "b"])
        rows_arg = stub_rdb["mock_table"].return_value.insert.call_args.args[0]
        assert {row["item_id"] for row in rows_arg} == {"a", "b"}
        assert all(row["item_type"] == "users" for row in rows_arg)
        assert all(row["created_at"] == "FAKE_NOW" for row in rows_arg)


class TestDeleteMigrationException:
    def test_dispatches_delete(self, stub_rdb):
        stub_rdb["Processed"].delete_migration_exception("ex-1")
        stub_rdb["mock_table"].assert_any_call("users_migrations_exceptions")
        stub_rdb["mock_table"].return_value.get.assert_called_with("ex-1")
        stub_rdb["mock_table"].return_value.get.return_value.delete.assert_called_once()
