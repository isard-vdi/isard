#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Usage parameter CRUD (table ``usage_parameter``).

A "usage parameter" is an admin-configured measurement formula for a
given item type (e.g. ``desktop.size`` evaluates the
``actual_size`` of a desktop's storage). System parameters cannot be
edited; only ``custom: True`` rows may be updated.
"""

from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from rethinkdb import r


class ParametersUsageProcessed(RethinkSharedConnection):
    """Layer-2 CRUD for ``usage_parameter`` rows."""

    @classmethod
    def list_parameters(cls, ids: list[str] | None = None) -> list[dict]:
        """Return all parameters, or just those whose id is in ``ids``."""
        with cls._rdb_context():
            if ids:
                return list(
                    r.table("usage_parameter")
                    .get_all(r.args(ids))
                    .run(cls._rdb_connection)
                )
            return list(r.table("usage_parameter").run(cls._rdb_connection))

    @classmethod
    def create_parameter(cls, data: dict) -> bool:
        """Insert a new parameter row.

        Picks just the fields the route accepts so callers can't smuggle
        through unknown keys.
        """
        with cls._rdb_context():
            r.table("usage_parameter").insert(
                {
                    "custom": data["custom"],
                    "default": 0,
                    "desc": data["desc"],
                    "formula": data["formula"],
                    "id": data["id"],
                    "item_type": data["item_type"],
                    "name": data["name"],
                    "units": data["units"],
                }
            ).run(cls._rdb_connection)
        return True

    @classmethod
    def update_parameter(cls, data: dict) -> bool:
        """Update a parameter; only ``custom: True`` rows may be edited."""
        from isardvdi_common.helpers.error_factory import Error

        if not data.get("custom"):
            raise Error("forbidden", "Only custom parameters can be edited")
        with cls._rdb_context():
            r.table("usage_parameter").get(data["id"]).update(data).run(
                cls._rdb_connection
            )
        return True

    @classmethod
    def delete_parameter(cls, parameter_id: str) -> bool:
        """Delete a parameter; raises ``not_found`` when nothing was deleted."""
        from isardvdi_common.helpers.error_factory import Error

        with cls._rdb_context():
            result = (
                r.table("usage_parameter")
                .get(parameter_id)
                .delete()
                .run(cls._rdb_connection)
            )
        if result.get("deleted", 0) == 0:
            raise Error(
                "not_found",
                "Parameter with ID " + parameter_id + " not found in database",
            )
        return True
