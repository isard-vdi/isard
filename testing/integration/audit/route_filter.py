# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pick which OpenAPI routes the audit will probe.

In-scope (per the approved plan):
- every ``/api/v4/admin/**`` path
- the top-50 high-traffic endpoints called by webapp / Vue 2 / Vue 3

Out-of-scope (skipped, recorded separately):
- multipart/form-data endpoints (audit only sends JSON in v1)
- endpoints that flip global state (maintenance, scheduler control)
- DELETE on seeded data (admin user, default category, default group)
- direct-viewer / register / password-reset specialty routers (need
  their own auth flows; out of scope for v1 audit)
"""

from __future__ import annotations

# Top-50 high-traffic endpoints from the Phase 1 frontend grep.
# Listed as (METHOD, PATH); paths use the OpenAPI {param} style.
TOP_50_FRONTEND_ROUTES: set[tuple[str, str]] = {
    # User-side desktops
    ("GET", "/api/v4/item/desktop/{desktop_id}"),
    ("GET", "/api/v4/item/desktop/{desktop_id}/get-details"),
    ("GET", "/api/v4/item/user/desktops"),
    ("GET", "/api/v4/item/user/get-details"),
    ("GET", "/api/v4/item/user/get-config"),
    ("GET", "/api/v4/item/user/get-quotas"),
    ("GET", "/api/v4/item/user/webapp-desktops"),
    ("GET", "/api/v4/item/user/webapp-templates"),
    ("GET", "/api/v4/item/user/get-allowed-hardware"),
    # Templates
    ("GET", "/api/v4/items/templates"),
    ("GET", "/api/v4/items/templates/get-allowed"),
    ("GET", "/api/v4/items/templates/get-shared"),
    # Media
    ("GET", "/api/v4/items/media"),
    ("GET", "/api/v4/items/media/get-allowed"),
    ("GET", "/api/v4/items/media/get-shared"),
    ("GET", "/api/v4/items/media/installs"),
    ("GET", "/api/v4/media/status"),
    ("GET", "/api/v4/quota/media/new"),
    # Storage pools
    ("GET", "/api/v4/storage-pool/availability"),
    # Recycle bin
    ("GET", "/api/v4/item/recycle-bin/get-default-delete-config"),
    ("GET", "/api/v4/item/recycle-bin/get-user-cutoff-time"),
    ("GET", "/api/v4/item/recycle-bin/count"),
    # Notifications
    ("GET", "/api/v4/notifications/status-bar"),
    # Login config
    ("GET", "/api/v4/item/login-config"),
    ("GET", "/api/v4/items/categories"),
    # Stats (lots of admin dashboards hit these)
    ("GET", "/api/v4/stats/users"),
    ("GET", "/api/v4/stats/desktops"),
    ("GET", "/api/v4/stats/desktops/status"),
    ("GET", "/api/v4/stats/templates"),
    ("GET", "/api/v4/stats/categories"),
    ("GET", "/api/v4/stats/hypervisors"),
    ("GET", "/api/v4/stats/categories/deployments"),
    ("GET", "/api/v4/stats/domains/status"),
    # Bookings
    ("GET", "/api/v4/items/bookings/all"),
    # Bastion
    ("GET", "/api/v4/bastion/config"),
}

# Multipart/form-data endpoints — skipped in v1, tracked separately.
SKIPPED_FORM_DATA: set[tuple[str, str]] = {
    ("POST", "/api/v4/admin/hypervisors"),
    # category/user logo+avatar uploads use multipart too — the audit
    # marks any 415 as "skipped: multipart" and continues.
}

# Endpoints that mutate global stack state — the audit must never touch
# these in default mode (they'd disrupt other parallel tests / users).
SKIPPED_GLOBAL_STATE: set[tuple[str, str]] = {
    ("PUT", "/api/v4/admin/maintenance/start"),
    ("PUT", "/api/v4/admin/maintenance/stop"),
    ("POST", "/api/v4/maintenance/text"),
    ("DELETE", "/api/v4/maintenance/text"),
}

# Endpoints that block the apiv4 event loop when exercised with a
# stub id. Empty since the Nextcloud ``start_login_auth`` flow was
# migrated from ``gevent.spawn`` to a daemon ``threading.Thread`` —
# the polling no longer starves the asyncio worker. See
# APIV4_THREADING_INCIDENT_ANALYSIS.md §7 Week 2.
SKIPPED_BLOCKING: set[tuple[str, str]] = set()

# Specialty routers that need their own auth flows — out of scope for v1.
SKIPPED_PATH_PREFIXES: tuple[str, ...] = (
    "/api/v4/register",
    "/api/v4/password_reset",
    "/api/v4/disclaimer",
    "/api/v4/direct_viewer",
    "/api/v4/migration",
)


def included_routes(
    spec: dict,
) -> list[tuple[str, str, dict]]:
    """Return ``(method, path, operation)`` triples to probe.

    ``operation`` is the OpenAPI operation object so callers can inspect
    parameters, requestBody, etc.
    """
    out: list[tuple[str, str, dict]] = []
    for path, methods in (spec.get("paths") or {}).items():
        if any(path.startswith(prefix) for prefix in SKIPPED_PATH_PREFIXES):
            continue
        for method_name, op in (methods or {}).items():
            if method_name not in {"get", "post", "put", "delete", "patch"}:
                continue
            method = method_name.upper()
            key = (method, path)
            if (
                key in SKIPPED_FORM_DATA
                or key in SKIPPED_GLOBAL_STATE
                or key in SKIPPED_BLOCKING
            ):
                continue
            in_scope = (
                path.startswith("/api/v4/admin/") or key in TOP_50_FRONTEND_ROUTES
            )
            if not in_scope:
                continue
            out.append((method, path, op))
    out.sort(key=lambda t: (t[1], t[0]))
    return out
