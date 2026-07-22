# SPDX-License-Identifier: AGPL-3.0-or-later

"""Hand-curated payloads for the top-N admin/management endpoints.

Each value is a callable ``(scratch) -> dict``. ``scratch`` is the
audit's ScratchEntities namespace + ids dict; callables can reference
``scratch.namespace``, ``scratch.user_id``, ``scratch.category_id``,
``scratch.group_id``, etc.

Sourced from grepping the actual frontend code:
- ``webapp/webapp/webapp/static/admin/js/users_management.js``
- ``webapp/webapp/webapp/static/admin/js/categories_management.js``
- ``webapp/webapp/webapp/static/admin/js/groups_management.js``
- ``component/frontend/src/`` for vue3 admin views

When the audit hits a (method, path) without an override, it falls back
to ``payload_factory.gen_sample`` against the OpenAPI requestBody.
"""

from __future__ import annotations

from typing import Callable

# Type alias: an override is a callable that, given the scratch entities,
# returns the JSON body to send. Returning {} means "send empty body".
OverrideFn = Callable[["object"], dict]


def _user_create(scratch) -> dict:
    return {
        "name": f"{scratch.namespace}_u",
        "email": "",
        "email-verified": "on",
        "role": "user",
        "category": "default",
        "group": "default-default",
        "password": "AuditPwd1!",
        "email_verified": True,
        "provider": "local",
        "bulk": False,
        "username": f"{scratch.namespace}_u",
    }


def _user_bulk_delete(scratch) -> dict:
    return {"user": [scratch.user_id], "delete_user": False}


def _category_create(scratch) -> dict:
    return {
        "name": f"{scratch.namespace}_c",
        "description": "audit-generated",
        "custom_url_name": f"{scratch.namespace}_c",
        "recycle": {"bin": {"cutoff": {"time": "1"}}},
        "frontend": False,
        "maintenance": False,
        "recycle_bin_cutoff_time": None,
        "manager_permissions": {
            "authentication": False,
            "branding": False,
            "login_notification": False,
            "plannings": False,
        },
    }


def _group_create(scratch) -> dict:
    return {
        "name": f"{scratch.namespace}_g",
        "description": "audit-generated",
        "parent_category": "default",
    }


def _user_edit(scratch) -> dict:
    return {
        "name": f"{scratch.namespace}_u_renamed",
        "email": "",
        "role": "user",
        "category": "default",
        "group": "default-default",
        "secondary_groups": [],
        "email_verified": True,
        "active": True,
    }


def _category_edit(scratch) -> dict:
    return {
        "id": scratch.category_id,
        "name": f"{scratch.namespace}_c_renamed",
        "description": "audit-edited",
    }


def _group_edit(scratch) -> dict:
    return {
        "id": scratch.group_id,
        "name": f"{scratch.namespace}_g_renamed",
        "description": "audit-edited",
    }


def _allowed_term(scratch) -> dict:
    return {"term": "admin", "category": "default"}


def _user_delete_check(scratch) -> dict:
    return {"ids": [scratch.user_id]}


OVERRIDES: dict[tuple[str, str], OverrideFn] = {
    ("POST", "/api/v4/admin/user"): _user_create,
    ("DELETE", "/api/v4/admin/user"): _user_bulk_delete,
    ("PUT", "/api/v4/admin/user/{user_id}"): _user_edit,
    ("POST", "/api/v4/admin/group"): _group_create,
    ("PUT", "/api/v4/admin/group/{group_id}"): _group_edit,
    ("POST", "/api/v4/admin/category"): _category_create,
    ("PUT", "/api/v4/admin/category/{category_id}"): _category_edit,
    ("POST", "/api/v4/admin/allowed/term/groups/{category_id}"): _allowed_term,
    ("POST", "/api/v4/admin/allowed/term/categories"): _allowed_term,
    ("POST", "/api/v4/admin/allowed/term/users/{category_id}"): _allowed_term,
    ("POST", "/api/v4/admin/user/delete/check"): _user_delete_check,
    ("POST", "/api/v4/admin/users/bulk"): lambda s: {
        "ids": [s.user_id],
        "active": True,
    },
}


def get_override(method: str, path: str) -> OverrideFn | None:
    return OVERRIDES.get((method.upper(), path))
