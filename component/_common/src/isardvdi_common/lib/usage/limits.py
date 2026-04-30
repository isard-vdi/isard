#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Usage limit CRUD (table ``usage_limit``).

A "usage limit" is a named tuple of ``hard``, ``soft``, ``exp_min``,
``exp_max`` thresholds applied to a usage parameter via
``usage_credit``. Validation enforces the canonical ordering
(``hard >= soft, exp_max, exp_min`` and ``exp_max > exp_min``,
``soft > exp_min``).
"""

from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from rethinkdb import r


def validate_usage_limits(limits: dict) -> None:
    """Validate the limit ordering invariants."""
    from isardvdi_common.helpers.error_factory import Error

    if not all(
        [
            limits["hard"] >= limits["exp_min"],
            limits["hard"] >= limits["exp_max"],
            limits["hard"] >= limits["soft"],
        ]
    ):
        raise Error(
            "bad_request",
            "The hard limit must be higher than or equal to all other limit values.",
        )
    if not (limits["exp_max"] > limits["exp_min"]):
        raise Error(
            "bad_request",
            "Expected maximum must be greater than the expected minimum",
        )
    if not (limits["soft"] > limits["exp_min"]):
        raise Error(
            "bad_request",
            "Expected minimum can not be greater than the soft limit",
        )


class LimitsUsageProcessed(RethinkSharedConnection):
    """Layer-2 CRUD for ``usage_limit`` rows."""

    @classmethod
    def list_limits(cls) -> list[dict]:
        """Return every limit row."""
        with cls._rdb_context():
            return list(r.table("usage_limit").run(cls._rdb_connection))

    @classmethod
    def create_limit(cls, name: str, desc: str, limits: dict) -> bool:
        """Insert a new limit after validating the ordering invariants."""
        validate_usage_limits(limits)
        with cls._rdb_context():
            r.table("usage_limit").insert(
                {"name": name, "desc": desc, "limits": limits}
            ).run(cls._rdb_connection)
        return True

    @classmethod
    def update_limit(cls, limit_id: str, name: str, desc: str, limits: dict) -> bool:
        """Update a limit after validating the ordering invariants."""
        validate_usage_limits(limits)
        with cls._rdb_context():
            r.table("usage_limit").get(limit_id).update(
                {"name": name, "desc": desc, "limits": limits}
            ).run(cls._rdb_connection)
        return True

    @classmethod
    def delete_limit(cls, limit_id: str) -> bool:
        """Delete a limit; raises ``not_found`` when nothing was deleted."""
        from isardvdi_common.helpers.error_factory import Error

        with cls._rdb_context():
            result = (
                r.table("usage_limit").get(limit_id).delete().run(cls._rdb_connection)
            )
        if result.get("deleted", 0) == 0:
            raise Error(
                "not_found",
                "Limit with ID " + limit_id + " not found in database",
            )
        return True
