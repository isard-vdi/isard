# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import uuid
from datetime import datetime, timezone

from isardvdi_common.api_exceptions import Error
from rethinkdb import r

from api import app

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)


def uuid_to_metadata_id(uuid_str: str) -> int:
    """Convert UUID to 64-bit metadata_id using lower 64 bits.

    The metadata_id is used for OpenFlow metadata-based isolation.
    Using lower 64 bits of UUID provides sufficient uniqueness.
    """
    u = uuid.UUID(uuid_str)
    return u.int & 0xFFFFFFFFFFFFFFFF


def get_user_networks(payload: dict) -> list:
    """Get user networks accessible to the current user.

    Returns networks that the user owns OR is allowed to access via the
    standard isardvdi 'allowed' schema.
    """
    user_id = payload["user_id"]
    category_id = payload["category_id"]
    group_id = payload["group_id"]
    role_id = payload["role_id"]

    with app.app_context():
        all_networks = list(r.table("user_networks").run(db.conn))

    # Admin sees all
    if role_id == "admin":
        return all_networks

    # Filter based on ownership and allowed schema
    result = []
    for net in all_networks:
        # Owner always has access
        if net.get("user") == user_id:
            result.append(net)
            continue

        # Manager sees all in their category
        if role_id == "manager" and net.get("category") == category_id:
            result.append(net)
            continue

        # Check allowed schema
        allowed = net.get("allowed", {})

        # roles: empty = everyone, False = nobody (owner only)
        if allowed.get("roles") is False:
            continue
        if allowed.get("roles") and role_id not in allowed["roles"]:
            if len(allowed["roles"]) > 0:
                continue

        # categories
        if allowed.get("categories") is not False:
            if len(allowed.get("categories", [])) == 0 or category_id in allowed.get(
                "categories", []
            ):
                result.append(net)
                continue

        # groups
        if allowed.get("groups") is not False:
            if len(allowed.get("groups", [])) == 0 or group_id in allowed.get(
                "groups", []
            ):
                result.append(net)
                continue

        # users
        if allowed.get("users") is not False:
            if user_id in allowed.get("users", []):
                result.append(net)
                continue

    return result


def get_user_network(network_id: str, payload: dict) -> dict:
    """Get a specific user network if accessible."""
    with app.app_context():
        network = r.table("user_networks").get(network_id).run(db.conn)

    if not network:
        raise Error("not_found", "Network not found")

    # Check access
    user_id = payload["user_id"]
    role_id = payload["role_id"]

    if role_id == "admin":
        return network
    if network.get("user") == user_id:
        return network
    if role_id == "manager" and network.get("category") == payload["category_id"]:
        return network

    # Check allowed schema (simplified)
    allowed = network.get("allowed", {})
    if allowed.get("roles") is False:
        raise Error("forbidden", "Access denied")

    # If we get here via allowed, return it
    # (Full check would replicate is_allowed logic)
    raise Error("forbidden", "Access denied")


def create_user_network(data: dict, payload: dict) -> dict:
    """Create a new user network.

    Args:
        data: Network data including name, description
        payload: User auth payload

    Returns:
        Created network with generated id and metadata_id
    """
    # Generate unique network_id and metadata_id with collision check
    with app.app_context():
        while True:
            network_id = str(uuid.uuid4())
            metadata_id = uuid_to_metadata_id(network_id)
            # Check uniqueness of metadata_id (extremely rare collision)
            existing = list(
                r.table("user_networks")
                .get_all(metadata_id, index="metadata_id")
                .limit(1)
                .run(db.conn)
            )
            if not existing:
                break
            # Collision detected - regenerate and try again

    now = datetime.now(timezone.utc).isoformat()

    network = {
        "id": network_id,
        "name": data.get("name", "Unnamed Network"),
        "description": data.get("description", ""),
        "kind": "user_network",
        "model": data.get("model", "virtio"),
        "qos_id": data.get("qos_id", "unlimited"),
        "metadata_id": metadata_id,
        # Standard isardvdi allowed schema
        "allowed": data.get(
            "allowed",
            {
                "roles": False,  # Owner only by default
                "categories": False,
                "groups": False,
                "users": [],
            },
        ),
        # Ownership
        "user": payload["user_id"],
        "group": payload["group_id"],
        "category": payload["category_id"],
        # Timestamps
        "created": now,
        "modified": now,
    }

    with app.app_context():
        r.table("user_networks").insert(network).run(db.conn)

    return network


def update_user_network(network_id: str, data: dict, payload: dict) -> dict:
    """Update a user network.

    Only owner, manager of category, or admin can update.
    """
    network = get_user_network(network_id, payload)

    # Check ownership for update
    if payload["role_id"] not in ["admin", "manager"]:
        if network.get("user") != payload["user_id"]:
            raise Error("forbidden", "Only owner can update network")

    # Fields that can be updated
    update_data = {"modified": datetime.now(timezone.utc).isoformat()}

    if "name" in data:
        update_data["name"] = data["name"]
    if "description" in data:
        update_data["description"] = data["description"]
    if "qos_id" in data:
        update_data["qos_id"] = data["qos_id"]
    if "allowed" in data:
        update_data["allowed"] = data["allowed"]

    with app.app_context():
        r.table("user_networks").get(network_id).update(update_data).run(db.conn)

    return {**network, **update_data}


def delete_user_network(network_id: str, payload: dict) -> bool:
    """Delete a user network.

    Only owner, manager of category, or admin can delete.
    """
    network = get_user_network(network_id, payload)

    # Check ownership for delete
    if payload["role_id"] not in ["admin", "manager"]:
        if network.get("user") != payload["user_id"]:
            raise Error("forbidden", "Only owner can delete network")

    with app.app_context():
        r.table("user_networks").get(network_id).delete().run(db.conn)

    return True
