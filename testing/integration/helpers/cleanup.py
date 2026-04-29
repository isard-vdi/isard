# SPDX-License-Identifier: AGPL-3.0-or-later

"""Additive cleanup helpers for integration tests.

We never nuke the DB; we only delete objects whose ``name`` starts with
a known prefix. Startup cleans prior-run leftovers; teardown cleans the
current run. A failing teardown must not abort the session — we log and
continue.
"""

from __future__ import annotations

import logging
from typing import Iterable

from .client import IsardClient

log = logging.getLogger("integration.cleanup")


def _safe_list(client: IsardClient, path: str, key: str | None = None) -> list:
    """GET a list endpoint; tolerate non-200 without aborting.

    Some apiv4 list endpoints return a bare list, others wrap it under a
    named key (``desktops``, ``templates``, ``media``, ``rows``). Pass
    ``key`` when the caller knows the expected wrapper.
    """
    resp = client.raw("GET", path)
    if resp.status_code != 200:
        log.warning("cleanup: GET %s -> HTTP %s; skipping", path, resp.status_code)
        return []
    payload = resp.json()
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for candidate in filter(None, (key, "rows", "desktops", "templates", "media")):
            if candidate in payload and isinstance(payload[candidate], list):
                return payload[candidate]
    return []


def _safe_delete(client: IsardClient, method: str, path: str) -> None:
    resp = client.raw(method, path)
    # 202 Accepted is success for queued deletions (e.g. media delete
    # dispatches an RQ task); 404 means "already gone" which is the
    # desired end-state for cleanup.
    if resp.status_code in (200, 202, 204, 404):
        return
    log.warning(
        "cleanup: %s %s -> HTTP %s; body=%s",
        method,
        path,
        resp.status_code,
        resp.text[:200],
    )


def cleanup_by_prefix(client: IsardClient, prefix: str) -> dict:
    """Delete every audit-owned object whose name starts with ``prefix``.

    Covers desktops / templates / media / downloaded domains (the
    original lifecycle-test scope) plus users / groups / categories
    (added so the audit harness can sweep its own scratch entities).
    Returns a per-kind count dict so tests can assert teardown.
    """
    counts = {
        "desktops": 0,
        "templates": 0,
        "media": 0,
        "downloads": 0,
        "users": 0,
        "groups": 0,
        "categories": 0,
    }

    for desktop in _safe_list(client, "/api/v4/items/desktops", key="desktops"):
        if _has_prefix(desktop, prefix):
            _safe_delete(client, "DELETE", f"/api/v4/item/desktop/{desktop['id']}")
            counts["desktops"] += 1

    for template in _safe_list(client, "/api/v4/items/templates", key="templates"):
        if _has_prefix(template, prefix):
            _safe_delete(client, "DELETE", f"/api/v4/item/template/{template['id']}")
            counts["templates"] += 1

    for media in _safe_list(client, "/api/v4/items/media", key="media"):
        if _has_prefix(media, prefix):
            _safe_delete(client, "DELETE", f"/api/v4/item/media/{media['id']}")
            counts["media"] += 1

    # Admin domain listing (kind=desktop). Catches downloaded desktops
    # still owned by the admin that haven't been deleted via the
    # user-facing endpoint, plus anything else named with our prefix.
    # The ``/admin/domains/name/desktop`` endpoint only returns
    # ``{name}`` (no id) — use the broader ``POST /admin/domains
    # kind=desktop`` listing which carries full rows.
    admin_resp = client.raw("POST", "/api/v4/admin/domains", json={"kind": "desktop"})
    if admin_resp.status_code == 200:
        for domain in admin_resp.json() or []:
            if not isinstance(domain, dict):
                continue
            if _has_prefix(domain, prefix) and domain.get("id"):
                _safe_delete(
                    client,
                    "POST",
                    f"/api/v4/admin/downloads/delete/domains/{domain['id']}",
                )
                counts["downloads"] += 1

    # Bulk-delete the user via the (only) DELETE /admin/user endpoint
    # which takes {"user": [ids], "delete_user": bool}. Skip the
    # protected built-in admin to avoid lockouts.
    user_ids_to_delete = []
    for user in _safe_list(client, "/api/v4/admin/users/management/users"):
        if _has_prefix(user, prefix):
            uid = user.get("id")
            if uid and uid != "local-default-admin-admin":
                user_ids_to_delete.append(uid)
    if user_ids_to_delete:
        resp = client.raw(
            "DELETE",
            "/api/v4/admin/user",
            json={"user": user_ids_to_delete, "delete_user": False},
        )
        if resp.status_code in (200, 202, 204):
            counts["users"] += len(user_ids_to_delete)
        else:
            log.warning(
                "cleanup: bulk delete users -> HTTP %s; body=%s",
                resp.status_code,
                resp.text[:200],
            )

    for group in _safe_list(client, "/api/v4/admin/users/management/groups"):
        if _has_prefix(group, prefix):
            gid = group.get("id")
            if gid and gid != "default-default":
                _safe_delete(client, "DELETE", f"/api/v4/admin/group/{gid}")
                counts["groups"] += 1

    for category in _safe_list(client, "/api/v4/admin/users/management/categories"):
        if _has_prefix(category, prefix):
            cid = category.get("id")
            if cid and cid != "default":
                _safe_delete(client, "DELETE", f"/api/v4/admin/category/{cid}")
                counts["categories"] += 1

    log.info("cleanup_by_prefix(%r): %s", prefix, counts)
    return counts


def _has_prefix(obj: dict, prefix: str) -> bool:
    name = obj.get("name") or ""
    return isinstance(name, str) and name.startswith(prefix)


def main() -> None:
    """CLI: ``python -m testing.integration.helpers.cleanup --prefix e2e_real_``"""
    import argparse
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="e2e_real_")
    parser.add_argument(
        "--user", default=os.environ.get("E2E_ADMIN_USER", "admin_e2e_01")
    )
    parser.add_argument(
        "--password", default=os.environ.get("E2E_ADMIN_PWD", "IsardTest1!")
    )
    parser.add_argument("--category", default="default")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    client = IsardClient()
    client.login(args.user, args.password, category_id=args.category)
    cleanup_by_prefix(client, args.prefix)


if __name__ == "__main__":  # pragma: no cover
    main()
