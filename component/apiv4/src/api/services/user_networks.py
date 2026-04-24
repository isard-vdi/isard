#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import uuid
from datetime import datetime, timezone

from api.services.error import Error
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from rethinkdb import r


def _uuid_to_metadata_id(uuid_str: str) -> int:
    """Convert UUID to 64-bit metadata_id using lower 64 bits."""
    u = uuid.UUID(uuid_str)
    return u.int & 0xFFFFFFFFFFFFFFFF


class UserNetworkService:

    @staticmethod
    def get_user_networks(payload: dict) -> list:
        """Get user networks accessible to the current user."""
        user_id = payload["user_id"]
        category_id = payload["category_id"]
        group_id = payload["group_id"]
        role_id = payload["role_id"]

        with RethinkSharedConnection._rdb_context():
            all_networks = list(
                r.table("user_networks").run(RethinkSharedConnection._rdb_connection)
            )

        if role_id == "admin":
            return all_networks

        result = []
        for net in all_networks:
            if net.get("user") == user_id:
                result.append(net)
                continue

            if role_id == "manager" and net.get("category") == category_id:
                result.append(net)
                continue

            allowed = net.get("allowed", {})

            if allowed.get("roles") is False:
                continue
            if allowed.get("roles") and role_id not in allowed["roles"]:
                if len(allowed["roles"]) > 0:
                    continue

            if allowed.get("categories") is not False:
                if len(
                    allowed.get("categories", [])
                ) == 0 or category_id in allowed.get("categories", []):
                    result.append(net)
                    continue

            if allowed.get("groups") is not False:
                if len(allowed.get("groups", [])) == 0 or group_id in allowed.get(
                    "groups", []
                ):
                    result.append(net)
                    continue

            if allowed.get("users") is not False:
                if user_id in allowed.get("users", []):
                    result.append(net)
                    continue

        return result

    @staticmethod
    def get_user_network(network_id: str, payload: dict) -> dict:
        """Get a specific user network if accessible."""
        with RethinkSharedConnection._rdb_context():
            network = (
                r.table("user_networks")
                .get(network_id)
                .run(RethinkSharedConnection._rdb_connection)
            )

        if not network:
            raise Error(
                "not_found",
                "Network not found",
                description_code="not_found",
            )

        user_id = payload["user_id"]
        role_id = payload["role_id"]

        if role_id == "admin":
            return network
        if network.get("user") == user_id:
            return network
        if role_id == "manager" and network.get("category") == payload["category_id"]:
            return network

        raise Error(
            "forbidden",
            "Access denied",
            description_code="forbidden",
        )

    @staticmethod
    def create_user_network(data, payload: dict) -> dict:
        """Create a new user network."""
        with RethinkSharedConnection._rdb_context():
            while True:
                network_id = str(uuid.uuid4())
                metadata_id = _uuid_to_metadata_id(network_id)
                existing = list(
                    r.table("user_networks")
                    .get_all(metadata_id, index="metadata_id")
                    .limit(1)
                    .run(RethinkSharedConnection._rdb_connection)
                )
                if not existing:
                    break

        now = datetime.now(timezone.utc).isoformat()

        allowed_data = (
            data.allowed.model_dump()
            if data.allowed
            else {
                "roles": False,
                "categories": False,
                "groups": False,
                "users": [],
            }
        )

        network = {
            "id": network_id,
            "name": data.name,
            "description": data.description,
            "kind": "user_network",
            "model": data.model,
            "qos_id": data.qos_id,
            "metadata_id": metadata_id,
            "allowed": allowed_data,
            "user": payload["user_id"],
            "group": payload["group_id"],
            "category": payload["category_id"],
            "created": now,
            "modified": now,
        }

        with RethinkSharedConnection._rdb_context():
            r.table("user_networks").insert(network).run(
                RethinkSharedConnection._rdb_connection
            )

        return network

    @staticmethod
    def update_user_network(network_id: str, data, payload: dict) -> dict:
        """Update a user network."""
        network = UserNetworkService.get_user_network(network_id, payload)

        if payload["role_id"] not in ["admin", "manager"]:
            if network.get("user") != payload["user_id"]:
                raise Error(
                    "forbidden",
                    "Only owner can update network",
                    description_code="forbidden",
                )

        update_data = {"modified": datetime.now(timezone.utc).isoformat()}

        if data.name is not None:
            update_data["name"] = data.name
        if data.description is not None:
            update_data["description"] = data.description
        if data.qos_id is not None:
            update_data["qos_id"] = data.qos_id
        if data.allowed is not None:
            update_data["allowed"] = data.allowed.model_dump()

        with RethinkSharedConnection._rdb_context():
            r.table("user_networks").get(network_id).update(update_data).run(
                RethinkSharedConnection._rdb_connection
            )

        return {**network, **update_data}

    @staticmethod
    def delete_user_network(network_id: str, payload: dict):
        """Delete a user network."""
        network = UserNetworkService.get_user_network(network_id, payload)

        if payload["role_id"] not in ["admin", "manager"]:
            if network.get("user") != payload["user_id"]:
                raise Error(
                    "forbidden",
                    "Only owner can delete network",
                    description_code="forbidden",
                )

        with RethinkSharedConnection._rdb_context():
            r.table("user_networks").get(network_id).delete().run(
                RethinkSharedConnection._rdb_connection
            )
