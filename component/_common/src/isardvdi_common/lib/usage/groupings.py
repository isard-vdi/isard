#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Usage parameter-grouping CRUD (table ``usage_grouping``).

A grouping bundles a set of parameter ids under a single name so credits
can target multiple parameters at once. Three system pseudo-groupings
(``_all`` / ``_system`` / ``_custom``) per item-type are synthesized
from the ``usage_parameter`` table on every read; user-defined
groupings live in ``usage_grouping``.
"""

from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from isardvdi_common.lib.usage.common import UsageProcessed
from rethinkdb import r


def _system_groupings_for(params_by_type: dict) -> list[dict]:
    """Synthesize three system groupings (_all / _system / _custom) per item_type."""
    groupings: list[dict] = []
    for item_type, params in params_by_type.items():
        system_parameters = [sp["id"] for sp in params if not sp["custom"]]
        custom_parameters = [cp["id"] for cp in params if cp["custom"]]
        groupings.extend(
            [
                {
                    "id": "_all",
                    "item_type": item_type,
                    "item_sub_type": "all",
                    "name": f"All {item_type} parameters",
                    "desc": f"All {item_type} system and custom parameters",
                    "parameters": system_parameters + custom_parameters,
                },
                {
                    "id": "_system",
                    "name": f"All {item_type} system parameters",
                    "item_type": item_type,
                    "item_sub_type": "system",
                    "desc": f"All {item_type} system parameters",
                    "parameters": system_parameters,
                },
                {
                    "id": "_custom",
                    "name": f"All {item_type} custom parameters",
                    "item_type": item_type,
                    "item_sub_type": "custom",
                    "desc": f"All {item_type} custom parameters",
                    "parameters": custom_parameters,
                },
            ]
        )
    return groupings


class GroupingsUsageProcessed(RethinkSharedConnection):
    """Layer-2 CRUD for ``usage_grouping`` rows + the system pseudo-groupings."""

    @classmethod
    def list_groupings(cls) -> list[dict]:
        """Return system pseudo-groupings + all user-defined grouping rows."""
        groupings = _system_groupings_for(UsageProcessed.get_params())
        with cls._rdb_context():
            groupings = groupings + list(
                r.table("usage_grouping").run(cls._rdb_connection)
            )
        return groupings

    @classmethod
    def get_groupings_dropdown(cls) -> dict:
        """Return groupings shaped for the admin dropdown UI.

        ``{"system": {item_type: [...]}, "custom": {item_type: [...]}}``
        — the route consumes this directly.
        """
        params = UsageProcessed.get_params()
        groupings: dict = {"system": {}, "custom": {}}
        for item_type in params:
            system_parameters = [
                sp["id"] for sp in params[item_type] if not sp["custom"]
            ]
            custom_parameters = [cp["id"] for cp in params[item_type] if cp["custom"]]
            groupings["system"][item_type] = [
                {
                    "id": "_all",
                    "name": f"All {item_type} parameters",
                    "item_type": item_type,
                    "desc": f"All {item_type} system and custom parameters",
                    "parameters": system_parameters + custom_parameters,
                },
                {
                    "id": "_system",
                    "name": f"All {item_type} system parameters",
                    "item_type": item_type,
                    "desc": f"All {item_type} system parameters",
                    "parameters": system_parameters,
                },
                {
                    "id": "_custom",
                    "name": f"All {item_type} custom parameters",
                    "item_type": item_type,
                    "desc": f"All {item_type} custom parameters",
                    "parameters": custom_parameters,
                },
            ]
            with cls._rdb_context():
                groupings["custom"][item_type] = list(
                    r.table("usage_grouping")
                    .filter({"item_type": item_type})
                    .run(cls._rdb_connection)
                )
        return groupings

    @classmethod
    def get_grouping(cls, grouping_id: str) -> dict:
        """Return a single grouping; falls back to system pseudo-groupings.

        Raises ``not_found`` if neither the user table nor the synthetic
        list contains ``grouping_id``.
        """
        from isardvdi_common.helpers.error_factory import Error

        with cls._rdb_context():
            grouping = (
                r.table("usage_grouping").get(grouping_id).run(cls._rdb_connection)
            )
        if grouping:
            return grouping
        synthetic = _system_groupings_for(UsageProcessed.get_params())
        matches = [g for g in synthetic if g.get("id") == grouping_id]
        if matches:
            return matches[0]
        raise Error("not_found", "Grouping not found")

    @classmethod
    def create_grouping(cls, data: dict) -> bool:
        """Insert a new user-defined grouping."""
        with cls._rdb_context():
            r.table("usage_grouping").insert(data).run(cls._rdb_connection)
        return True

    @classmethod
    def update_grouping(cls, data: dict) -> bool:
        """Update a grouping by id (``data["id"]``)."""
        with cls._rdb_context():
            r.table("usage_grouping").get(data["id"]).update(data).run(
                cls._rdb_connection
            )
        return True

    @classmethod
    def delete_grouping(cls, grouping_id: str) -> bool:
        """Delete a grouping; raises ``not_found`` when nothing was deleted."""
        from isardvdi_common.helpers.error_factory import Error

        with cls._rdb_context():
            result = (
                r.table("usage_grouping")
                .get(grouping_id)
                .delete()
                .run(cls._rdb_connection)
            )
        if result.get("deleted", 0) == 0:
            raise Error(
                "not_found",
                "Parameter grouping with ID " + grouping_id + " not found in database",
            )
        return True
