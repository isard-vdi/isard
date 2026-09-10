# SPDX-License-Identifier: AGPL-3.0-or-later

"""Additive teardown for integration tests.

We never nuke the DB — only delete objects whose ``name`` starts with a
known prefix, all through the generated client (so a renamed delete / list
route breaks at import time instead of turning teardown into a silent
no-op). A failing teardown must never abort the session, so each kind
swallows its own error.

Kept as a module (implementation + a ``python -m`` CLI) so existing
``from .helpers.cleanup import cleanup_by_prefix`` imports and the
``python -m testing.integration.helpers.cleanup`` entrypoint keep working.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from isardvdi_apiv4_client.api.role_admin import admin_delete_category
from isardvdi_apiv4_client.api.role_advanced import delete_media, delete_template
from isardvdi_apiv4_client.api.role_manager import (
    admin_delete_group,
    admin_delete_users,
    admin_get_templates,
    admin_list_categories_nav,
    admin_list_domains,
    admin_list_groups_nav,
    admin_list_users_nav,
    admin_media_list,
)
from isardvdi_apiv4_client.api.role_user import delete_desktop
from isardvdi_apiv4_client.models.admin_list_categories_nav_nav import (
    AdminListCategoriesNavNav,
)
from isardvdi_apiv4_client.models.admin_list_domains_data import AdminListDomainsData
from isardvdi_apiv4_client.models.admin_list_domains_data_kind import (
    AdminListDomainsDataKind,
)
from isardvdi_apiv4_client.models.admin_list_groups_nav_nav import AdminListGroupsNavNav
from isardvdi_apiv4_client.models.admin_list_users_nav_nav import AdminListUsersNavNav
from isardvdi_apiv4_client.models.admin_user_delete_data import AdminUserDeleteData

if TYPE_CHECKING:
    from .client import IsardClient

log = logging.getLogger("integration.cleanup")

__all__ = ["cleanup_by_prefix"]


def _name(item: Any) -> str:
    """``name`` as a plain string, tolerating ``Unset`` / missing."""
    name = getattr(item, "name", "")
    return name if isinstance(name, str) else ""


def cleanup_by_prefix(ic: IsardClient, prefix: str) -> dict:
    """Best-effort sweep of every object whose name starts with ``prefix``
    (desktops / templates / media / users / groups / categories).

    A fresh apiv4 client is built so the caller's token refresh is picked
    up; each kind swallows its own error so a failing teardown never masks
    a real test failure.
    """
    client = ic.apiv4()
    counts = {
        k: 0
        for k in ("desktops", "templates", "media", "users", "groups", "categories")
    }

    def _try(label: str, fn) -> None:
        try:
            fn()
        except Exception as exc:  # pragma: no cover - teardown best-effort
            log.warning("cleanup %s: %s", label, exc)

    def _desktops() -> None:
        resp = admin_list_domains.sync_detailed(
            client=client,
            body=AdminListDomainsData(kind=AdminListDomainsDataKind.DESKTOP),
        )
        for d in resp.parsed if isinstance(resp.parsed, list) else []:
            if _name(d).startswith(prefix):
                delete_desktop.sync_detailed(desktop_id=d.id, client=client)
                counts["desktops"] += 1

    def _templates() -> None:
        resp = admin_get_templates.sync_detailed(client=client)
        for t in resp.parsed if isinstance(resp.parsed, list) else []:
            if _name(t).startswith(prefix):
                delete_template.sync_detailed(template_id=t.id, client=client)
                counts["templates"] += 1

    def _media() -> None:
        resp = admin_media_list.sync_detailed(client=client)
        for m in resp.parsed if isinstance(resp.parsed, list) else []:
            if _name(m).startswith(prefix):
                delete_media.sync_detailed(media_id=m.id, client=client)
                counts["media"] += 1

    def _users() -> None:
        resp = admin_list_users_nav.sync_detailed(
            nav=AdminListUsersNavNav.MANAGEMENT, client=client
        )
        ids = [
            u.id
            for u in (resp.parsed if isinstance(resp.parsed, list) else [])
            if _name(u).startswith(prefix) and u.id != "local-default-admin-admin"
        ]
        if ids:
            admin_delete_users.sync_detailed(
                client=client,
                body=AdminUserDeleteData(user=ids, delete_user=False),
            )
            counts["users"] += len(ids)

    def _groups() -> None:
        resp = admin_list_groups_nav.sync_detailed(
            nav=AdminListGroupsNavNav.MANAGEMENT, client=client
        )
        for g in resp.parsed if isinstance(resp.parsed, list) else []:
            if _name(g).startswith(prefix) and g.id != "default-default":
                admin_delete_group.sync_detailed(group_id=g.id, client=client)
                counts["groups"] += 1

    def _categories() -> None:
        resp = admin_list_categories_nav.sync_detailed(
            nav=AdminListCategoriesNavNav.MANAGEMENT, client=client
        )
        for c in resp.parsed if isinstance(resp.parsed, list) else []:
            if _name(c).startswith(prefix) and c.id != "default":
                admin_delete_category.sync_detailed(category_id=c.id, client=client)
                counts["categories"] += 1

    for label, fn in (
        ("desktops", _desktops),
        ("templates", _templates),
        ("media", _media),
        ("users", _users),
        ("groups", _groups),
        ("categories", _categories),
    ):
        _try(label, fn)

    log.info("cleanup_by_prefix(%r): %s", prefix, counts)
    return counts


def main() -> None:
    """CLI: ``python -m testing.integration.helpers.cleanup --prefix e2e_real_``"""
    import argparse
    import os

    from .client import IsardClient

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
