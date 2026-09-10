#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""
Centralized test data factories.

Each factory returns a dict with sensible defaults. Override any field
by passing it as a keyword argument. Tests should only specify the
fields relevant to their assertion.
"""


def make_user(*, jwt=None, **overrides):
    """Build a minimal valid user document.

    If *jwt* is a MockJWT, populate identity fields from its payload.
    """
    if jwt:
        p = jwt.payload
        defaults = {
            "id": p["user_id"],
            "category": p["category_id"],
            "group": p["group_id"],
            "name": p["name"],
            "username": p["name"],
            "provider": p["provider"],
            "role": p["role_id"],
            "uid": p["name"],
        }
    else:
        defaults = {
            "id": "local-default-admin-admin",
            "category": "default",
            "group": "default-default",
            "name": "Administrator",
            "username": "Administrator",
            "provider": "local",
            "role": "admin",
            "uid": "Administrator",
        }
    defaults.update(
        {
            "password": "f0ckt3Rf$",
            "lang": "en",
            "accessed": 1234567890,
            "photo": "",
        }
    )
    defaults.update(overrides)
    return defaults


def make_category(**overrides):
    """Build a minimal valid category document."""
    defaults = {
        "id": "default",
        "name": "Default Category",
        "uid": "default",
        "custom_url_name": "default_url",
        "frontend": True,
    }
    defaults.update(overrides)
    return defaults


def make_group(**overrides):
    """Build a minimal valid group document."""
    defaults = {
        "id": "default-default",
        "name": "Default",
        "parent_category": "default",
        "description": "",
        "enrollment": {"manager": False, "advanced": False, "user": False},
    }
    defaults.update(overrides)
    return defaults


def make_config(**overrides):
    """Build a minimal valid config document."""
    defaults = {
        "id": 1,
        "maintenance": False,
    }
    defaults.update(overrides)
    return defaults


def make_db(**table_overrides):
    """Build a default mock DB with config + categories.

    Pass table names as keyword arguments to override or add tables::

        make_db(users=[make_user(jwt=jwt)], domains=[...])
    """
    db = {
        "config": [make_config()],
        "categories": [make_category()],
    }
    db.update(table_overrides)
    return db
