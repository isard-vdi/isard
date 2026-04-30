#
#   Copyright © 2026 IsardVDI
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from rethinkdb import r


class UsersAuthenticationProcessed(RethinkSharedConnection):
    """Data-access for the ``authentication`` table (policies) plus the
    cross-table ops the admin authentication endpoint needs:

    * ``users`` — clear ``policy_field`` on a force-policy-at-login pass.
    * ``users`` — pluck ``role``/``lang``/``provider`` for the disclaimer.
    * ``notification_tmpls`` — read disclaimer templates.
    * ``users_migrations_exceptions`` — list / add / delete the per-item
      migration opt-outs.

    All policy CRUD validation / authz lives in the apiv4 service; this
    class is the persistence layer.
    """

    _rdb_table = "authentication"

    # ── Policies (authentication table) ──────────────────────────────────

    @classmethod
    def insert_policy(cls, data: dict) -> None:
        """Insert a new policy row. Caller validates duplicates first."""
        with cls._rdb_context():
            r.table(cls._rdb_table).insert(data).run(cls._rdb_connection)

    @classmethod
    def list_policies_with_category_name(cls) -> list:
        """List all policies, augmenting each with ``category_name``.

        ``category == "all"`` is rendered as the literal string ``"all"``;
        otherwise the categories table is joined to fetch the human name,
        falling back to ``"[DELETED]"`` when the row is gone.
        """
        with cls._rdb_context():
            return list(
                r.table(cls._rdb_table)
                .merge(
                    lambda policy: {
                        "category_name": (
                            r.branch(
                                policy["category"] == "all",
                                "all",
                                r.table("categories")
                                .get(policy["category"])
                                .default({"name": "[DELETED]"})["name"],
                            )
                        )
                    }
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_policy(cls, policy_id: str) -> dict:
        """Get a single policy or raise ``not_found``.

        Without this, every caller (delete_policy / force_policy_at_login
        / edit_policy) crashes with ``TypeError: 'NoneType' is not
        subscriptable`` and surfaces as a generic 500 instead of a typed
        404.
        """
        with cls._rdb_context():
            policy = r.table(cls._rdb_table).get(policy_id).run(cls._rdb_connection)
        if policy is None:
            raise Error(
                "not_found",
                f"Authentication policy {policy_id} not found",
                description_code="auth_policy_not_found",
            )
        return policy

    @classmethod
    def update_policy(cls, policy_id: str, data: dict) -> None:
        """Apply ``data`` to a policy row (idempotent on missing row)."""
        with cls._rdb_context():
            r.table(cls._rdb_table).get(policy_id).update(data).run(cls._rdb_connection)

    @classmethod
    def delete_policy(cls, policy_id: str) -> None:
        """Delete a policy row."""
        with cls._rdb_context():
            r.table(cls._rdb_table).get(policy_id).delete().run(cls._rdb_connection)

    @classmethod
    def has_duplicate_policy(cls, category: str, role: str, type_: str) -> bool:
        """Return ``True`` when a policy with the given (category, role,
        type) tuple already exists.

        Backs the conflict-409 check in the policy-create path.
        """
        with cls._rdb_context():
            return (
                len(
                    list(
                        r.table(cls._rdb_table)
                        .get_all([category, role], index="category-role")
                        .filter({"type": type_})
                        .run(cls._rdb_connection)
                    )
                )
                > 0
            )

    # ── Force policy at login (users table) ──────────────────────────────

    @classmethod
    def force_policy_at_login(cls, policy: dict, policy_field: str) -> None:
        """Clear ``policy_field`` on every user matching ``policy``'s
        scope (provider, optional category, optional role).

        Setting the field to ``None`` is what the auth flow checks to
        force the user through the policy validator at next login.
        """
        with cls._rdb_context():
            query = r.table("users").get_all(policy["type"], index="provider")
            if policy["category"] != "all":
                query = query.filter({"category": policy["category"]})
            if policy["role"] != "all":
                query = query.filter({"role": policy["role"]})
            query.update({policy_field: None}).run(cls._rdb_connection)

    # ── Disclaimer ───────────────────────────────────────────────────────

    @classmethod
    def get_user_disclaimer_fields(cls, user_id: str) -> dict:
        """Pluck ``role`` / ``lang`` / ``provider`` for a user — the
        only fields the disclaimer-template lookup needs.
        """
        with cls._rdb_context():
            return (
                r.table("users")
                .get(user_id)
                .pluck("role", "lang", "provider")
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_notification_template(cls, template_id: str) -> dict | None:
        """Read a notification template row by id.

        Returns None when missing — the caller decides whether that's a
        404 or a fall-back-to-default.
        """
        with cls._rdb_context():
            return (
                r.table("notification_tmpls").get(template_id).run(cls._rdb_connection)
            )

    # ── Migration exceptions (users_migrations_exceptions) ───────────────

    @classmethod
    def list_migration_exceptions_with_item_name(cls) -> list:
        """List all migration exceptions augmenting each row with the
        target item's ``name`` from its source table.
        """
        with cls._rdb_context():
            return list(
                r.table("users_migrations_exceptions")
                .merge(
                    lambda exception: {
                        "item_name": r.table(exception["item_type"]).get(
                            exception["item_id"]
                        )["name"]
                    }
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_existing_migration_exception_ids(cls, item_ids: list[str]) -> set[str]:
        """Return the subset of ``item_ids`` that already have an
        exception row registered.

        Used to dedupe new exceptions before inserting.
        """
        if not item_ids:
            return set()
        with cls._rdb_context():
            return set(
                r.table("users_migrations_exceptions")
                .get_all(*item_ids, index="item_id")["item_id"]
                .run(cls._rdb_connection)
            )

    @classmethod
    def insert_migration_exceptions(
        cls, item_type: str, new_item_ids: list[str]
    ) -> None:
        """Bulk-insert exception rows for the supplied item ids.

        ``r.now()`` stamps ``created_at`` server-side so the timestamp
        reflects when the row landed in rdb, not when the caller built
        the dict.
        """
        if not new_item_ids:
            return
        rows = [
            {
                "item_type": item_type,
                "item_id": item_id,
                "created_at": r.now(),
            }
            for item_id in new_item_ids
        ]
        with cls._rdb_context():
            r.table("users_migrations_exceptions").insert(rows).run(cls._rdb_connection)

    @classmethod
    def delete_migration_exception(cls, exception_id: str) -> None:
        """Delete one migration exception by id."""
        with cls._rdb_context():
            r.table("users_migrations_exceptions").get(exception_id).delete().run(
                cls._rdb_connection
            )
