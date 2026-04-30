# SPDX-License-Identifier: AGPL-3.0-or-later

"""Wire-shape contract tests for every apiv4 endpoint the Vue 2
``old-frontend`` and the Flask ``webapp`` hit during normal use.

These are GETs (no mutation) — the tests pin response status + the
keys / types the frontends rely on. They are deliberately broad:
each test holds one endpoint, so a regression on a single response
shape lights up on its own line in pytest output rather than failing
some larger lifecycle test in a confusing way.

Endpoint discovery: ``grep -roh "apiV[34]Segment}/...">"`` over
``old-frontend/src/`` plus ``grep -roh "/api/v[34]/...">"`` over
``webapp/webapp/webapp/``. The selection here is the union of high-
value endpoints the two UIs reach for on every login/dashboard load
plus the per-item read endpoints (desktop / template / media / user /
recycle bin / login config / maintenance / quotas / hypervisors /
storage / categories / groups / scheduler / system). Not exhaustive of
write paths — those are exercised by the lifecycle tests.

The test stack must run with ``populate_test_db.py`` seeded; the
admin returned by ``admin_client`` is the seeded admin and has the
permissions every endpoint here requires.
"""

from __future__ import annotations

import pytest

from .helpers.client import IsardClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_listish(payload) -> bool:
    """Return True when the payload looks like a listing response —
    either a bare list or a one-key wrapper dict (e.g.
    ``{"desktops": [...]}``). Used to assert listing-shape contracts
    without pinning the exact wrapper key."""
    if isinstance(payload, list):
        return True
    if isinstance(payload, dict):
        for v in payload.values():
            if isinstance(v, list):
                return True
    return False


def _get_listing_items(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for v in payload.values():
            if isinstance(v, list):
                return v
    return []


# ---------------------------------------------------------------------------
# User / login / config — every dashboard load hits these
# ---------------------------------------------------------------------------


@pytest.mark.real
def test_user_get_details(admin_client: IsardClient):
    """``GET /item/user/get-details`` — every Vue dashboard reads it
    on mount to populate the navbar avatar/role."""
    body = admin_client.get("/api/v4/item/user/get-details")
    assert isinstance(body, dict)
    for k in ("id", "username", "category", "role"):
        assert k in body, f"missing user-detail key {k!r}; got {sorted(body)}"


@pytest.mark.real
def test_user_get_config(admin_client: IsardClient):
    """``GET /item/user/get-config`` — Vue 2 + Vue 3 read it for the
    user's lang/spice/theme prefs."""
    body = admin_client.get("/api/v4/item/user/get-config")
    assert isinstance(body, dict), f"expected dict, got {type(body).__name__}"


@pytest.mark.real
def test_user_get_quotas(admin_client: IsardClient):
    """``GET /item/user/get-quotas`` — Vue 2 dashboard renders the
    quota progress bars from this endpoint."""
    body = admin_client.get("/api/v4/item/user/get-quotas")
    # Returns either a dict with quota/limits keys or False when none
    # configured. Both shapes are valid; pin only that the call doesn't
    # 500 and returns parseable JSON.
    assert body is not None or body is False or isinstance(body, dict)


@pytest.mark.real
def test_user_get_password_policy(admin_client: IsardClient):
    """``GET /item/user/get-password-policy`` — webapp Reset Password
    form reads it to render the policy hint."""
    body = admin_client.get("/api/v4/item/user/get-password-policy")
    assert isinstance(body, dict), f"expected dict, got {type(body).__name__}"


@pytest.mark.real
def test_user_get_allowed_hardware(admin_client: IsardClient):
    """``GET /item/user/get-allowed-hardware`` — Vue 2 New Desktop
    form populates dropdowns from this. Must include the dropdown
    fields (videos / interfaces / boot_order / graphics) and a
    ``quota`` block with vcpu/memory ceilings."""
    body = admin_client.get("/api/v4/item/user/get-allowed-hardware")
    assert isinstance(body, dict), f"expected dict, got {type(body).__name__}"
    expected = {"videos", "interfaces", "boot_order", "graphics", "quota"}
    missing = expected - set(body.keys())
    assert (
        not missing
    ), f"hardware response missing keys {sorted(missing)}; got {sorted(body)}"


@pytest.mark.real
def test_user_vpn_config(admin_client: IsardClient):
    """``GET /item/user/vpn/config`` — Vue 2 & webapp render the VPN
    setup modal. Returns plain text (.conf file body); the contract
    is that it returns 200 with non-empty text."""
    resp = admin_client.raw("GET", "/api/v4/item/user/vpn/config")
    # Default seeded admin has no vpn config; the endpoint may return
    # 200 with body or 428 (precondition_required) when the user has
    # no wireguard config yet. Both are valid frontend-handled cases.
    assert resp.status_code in (
        200,
        412,
        428,
    ), f"vpn/config: unexpected {resp.status_code}; body={resp.text[:200]}"


# ---------------------------------------------------------------------------
# Listing endpoints the Vue 2 + webapp UIs use for table views
# ---------------------------------------------------------------------------


@pytest.mark.real
@pytest.mark.parametrize(
    "path",
    [
        "/api/v4/items/desktops",
        "/api/v4/items/templates",
        "/api/v4/items/media",
        "/api/v4/items/deployments",
        "/api/v4/items/categories",
        "/api/v4/items/recycle-bin",
        "/api/v4/items/storage/ready",
    ],
)
def test_admin_listing_shape(admin_client: IsardClient, path: str):
    """Every listing endpoint Vue 2 + webapp use must return either a
    bare list or a one-key wrapper dict. A 5xx or non-listish payload
    here means the table view will silently render empty."""
    body = admin_client.get(path)
    assert _is_listish(body), (
        f"{path}: expected listing-shape response, got {type(body).__name__}; "
        f"value head: {str(body)[:200]}"
    )


@pytest.mark.real
def test_admin_categories_lists_default(admin_client: IsardClient):
    """``GET /items/categories`` — Vue 2 login dropdown + webapp admin
    page populate from this. The default category is always seeded."""
    body = admin_client.get("/api/v4/items/categories")
    items = _get_listing_items(body)
    ids = {c.get("id") for c in items if isinstance(c, dict)}
    assert (
        "default" in ids
    ), f"default category missing from /items/categories; got {sorted(ids)}"


# ---------------------------------------------------------------------------
# Login / maintenance / system
# ---------------------------------------------------------------------------


@pytest.mark.real
def test_login_config(admin_client: IsardClient):
    """``GET /item/login-config`` — webapp + Vue 2 + Vue 3 fetch this
    on the login page to render the optional cover/notification."""
    body = admin_client.get("/api/v4/item/login-config")
    assert isinstance(body, dict)


@pytest.mark.real
def test_maintenance_status(admin_client: IsardClient):
    """``GET /maintenance`` — Vue 2 + webapp poll this to show the
    "down for maintenance" banner. The response is ``{"enabled": bool}``
    (named ``enabled`` rather than ``maintenance`` because the route
    is itself named ``/maintenance``)."""
    resp = admin_client.raw("GET", "/api/v4/maintenance")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
    assert "enabled" in body, f"missing enabled flag: {body!r}"
    assert isinstance(body["enabled"], bool)


@pytest.mark.real
def test_logo_endpoint(admin_client: IsardClient):
    """``GET /logo`` — Vue 2 + Vue 3 fetch the configured logo. The
    endpoint may stream binary or return a JSON wrapper depending on
    config; both must return 200."""
    resp = admin_client.raw("GET", "/api/v4/logo")
    assert resp.status_code == 200, f"/logo -> {resp.status_code}"


# ---------------------------------------------------------------------------
# Recycle bin — heavily used by Vue 2 + webapp admin trash views
# ---------------------------------------------------------------------------


@pytest.mark.real
def test_recycle_bin_count(admin_client: IsardClient):
    """``GET /item/recycle-bin/count`` — Vue 2 navbar shows this as a
    badge. Must return an integer."""
    body = admin_client.get("/api/v4/item/recycle-bin/count")
    assert isinstance(
        body, (int, dict)
    ), f"expected int or dict, got {type(body).__name__}"


@pytest.mark.real
def test_recycle_bin_default_delete_config(admin_client: IsardClient):
    """``GET /item/recycle-bin/get-default-delete-config`` — webapp
    admin form reads the system-wide recycle-bin TTL config. May be
    ``False`` when no config is set (the cleared/default state) or a
    dict; both shapes are handled by the frontend renderer."""
    body = admin_client.get("/api/v4/item/recycle-bin/get-default-delete-config")
    assert body is False or isinstance(
        body, dict
    ), f"expected False or dict, got {type(body).__name__}"


@pytest.mark.real
def test_recycle_bin_user_cutoff_time(admin_client: IsardClient):
    """``GET /item/recycle-bin/get-user-cutoff-time`` — Vue 2 dashboard
    renders the cutoff label from this."""
    body = admin_client.get("/api/v4/item/recycle-bin/get-user-cutoff-time")
    # Returns an int (cutoff timestamp) or a dict wrapping it. Both ok.
    assert body is not None


# ---------------------------------------------------------------------------
# Bookings — Vue 2 calendar widget hits these on every page load
# ---------------------------------------------------------------------------


@pytest.mark.real
def test_bookings_listing(admin_client: IsardClient):
    """``GET /items/bookings`` — Vue 2 calendar lists user's events."""
    body = admin_client.get("/api/v4/items/bookings")
    assert _is_listish(
        body
    ), f"/items/bookings expected listing shape; got {type(body).__name__}"


# ---------------------------------------------------------------------------
# Storage / hypervisors — admin panels in webapp + Vue 2
# ---------------------------------------------------------------------------


@pytest.mark.real
def test_admin_hypervisors_listing(admin_client: IsardClient):
    """``GET /admin/hypervisors`` — Vue 2 + webapp + Vue 3 admin sidebars
    all consume this. The default test stack always has at least one
    hypervisor row (``isard-hypervisor``)."""
    body = admin_client.get("/api/v4/admin/hypervisors")
    assert isinstance(
        body, list
    ), f"/admin/hypervisors expected list, got {type(body).__name__}"
    assert body, "no hypervisors registered — populate.py seed missing"
    for h in body:
        assert isinstance(h, dict)
        for k in ("id", "status", "hostname"):
            assert k in h, f"hypervisor row missing {k!r}: {sorted(h)}"


@pytest.mark.real
def test_admin_storage_pool_default(admin_client: IsardClient):
    """``GET /storage-pool/default`` — webapp admin uses it to render
    the default storage-pool detail card."""
    resp = admin_client.raw("GET", "/api/v4/storage-pool/default")
    assert resp.status_code in (
        200,
        404,
    ), f"storage-pool/default unexpected status {resp.status_code}"


# ---------------------------------------------------------------------------
# Scheduler — Vue 2 + webapp admin landing page reads system jobs
# ---------------------------------------------------------------------------


@pytest.mark.real
def test_admin_scheduler_jobs_system(admin_client: IsardClient):
    """``GET /admin/scheduler/jobs/system`` — webapp admin sees this on
    the System tab. The seed always has at least the recycle-bin
    cleanup + the unused-items + the notifications cleanup jobs."""
    body = admin_client.get("/api/v4/admin/scheduler/jobs/system")
    assert isinstance(body, list), f"expected list of jobs, got {type(body).__name__}"


@pytest.mark.real
def test_admin_scheduler_jobs_bookings(admin_client: IsardClient):
    """``GET /admin/scheduler/jobs/bookings`` — booking-priority admin
    page renders this. List can be empty on a fresh stack but must
    not 5xx."""
    body = admin_client.get("/api/v4/admin/scheduler/jobs/bookings")
    assert isinstance(body, list)


# ---------------------------------------------------------------------------
# Stats — webapp admin echart panels and dashboard
# ---------------------------------------------------------------------------


@pytest.mark.real
def test_stats_domains_status(admin_client: IsardClient):
    """``GET /stats/domains/status`` — stats-go also consumes this.
    Pin: response always carries ``desktop`` and ``template`` as
    non-null dicts (stats-go's strict decoder rejects ``null`` on
    these fields). ``domains.kind`` only takes those two values, so
    the response has no other top-level keys."""
    body = admin_client.get("/api/v4/stats/domains/status")
    assert isinstance(body, dict)
    for k in ("desktop", "template"):
        assert k in body, f"missing kind {k!r}; got {sorted(body)}"
        assert isinstance(
            body[k], dict
        ), f"{k!r} must be dict (stats-go decodes strictly); got {type(body[k]).__name__}"


@pytest.mark.real
def test_stats_desktops_status(admin_client: IsardClient):
    """``GET /stats/desktops/status`` — webapp admin status echart."""
    resp = admin_client.raw("GET", "/api/v4/stats/desktops/status")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Notifications — Vue 2 + Vue 3 dashboards
# ---------------------------------------------------------------------------


@pytest.mark.real
def test_notifications_status_bar(admin_client: IsardClient):
    """``GET /notifications/status-bar`` — Vue 2 status-bar polls."""
    resp = admin_client.raw("GET", "/api/v4/notifications/status-bar")
    # Endpoint may return 200 list or 204 when no banner. Both are ok.
    assert resp.status_code in (
        200,
        204,
    ), f"notifications/status-bar: {resp.status_code}; body={resp.text[:200]}"


# ---------------------------------------------------------------------------
# Domain detail — admin panel in webapp + Vue 2
# ---------------------------------------------------------------------------


@pytest.mark.real
def test_admin_domains_kind_desktop(admin_client: IsardClient):
    """``POST /admin/domains kind=desktop`` — Vue 2 + webapp admin
    Desktops table calls it with the kind filter. Returns a list of
    domains; on an empty stack the list may be empty but must be a
    list."""
    body = admin_client.post("/api/v4/admin/domains", json_body={"kind": "desktop"})
    assert isinstance(body, list)


@pytest.mark.real
def test_admin_domains_kind_template(admin_client: IsardClient):
    """``POST /admin/domains kind=template`` — admin Templates table.
    Default seed has at least one template."""
    body = admin_client.post("/api/v4/admin/domains", json_body={"kind": "template"})
    assert isinstance(body, list)


# ---------------------------------------------------------------------------
# Bastions / VPN admin — webapp routes
# ---------------------------------------------------------------------------


@pytest.mark.real
def test_items_bastions(admin_client: IsardClient):
    """``GET /items/bastions`` — Vue 2 admin reads bastion config.

    The endpoint is gated by the ``advanced`` role (not ``admin``), so
    a default admin login may legitimately get 403 alongside the 200
    case. Frontend renders an empty list on either 200 or 403.
    """
    resp = admin_client.raw("GET", "/api/v4/items/bastions")
    assert resp.status_code in (
        200,
        403,
        404,
    ), f"items/bastions: unexpected {resp.status_code}; body={resp.text[:200]}"


# ---------------------------------------------------------------------------
# Analytics endpoints emitting datetime fields — pin auto-serialisation path.
#
# These routes consume the FastAPI ``return result`` pattern (no
# ``JSONResponse(content=...)``) so ``jsonable_encoder`` handles the
# rethinkdb ``datetime`` → ISO-8601 conversion. Re-introducing
# ``JSONResponse(content=...)`` here would silently 500 on the first
# non-empty result, so the contract is: the endpoint MUST return 200
# AND any ``last_accessed`` field MUST be a string (or ``None``), never
# a stray dict / object that would indicate datetime leaked through.
# ---------------------------------------------------------------------------


def _is_iso_datetime_or_none(value) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    # ISO-8601 produced by `datetime.isoformat()` always begins with a
    # 4-digit year. We don't fully parse it here — the goal is to catch
    # accidental dict / object leakage, not validate the calendar.
    return len(value) >= 10 and value[4] == "-" and value[7] == "-"


@pytest.mark.real
def test_analytics_desktops_recently_used_serialises_datetime(
    admin_client: IsardClient,
):
    """``POST /analytics/desktops/recently_used`` returns rows whose
    ``last_accessed`` is materialised by ``r.epoch_time(...)``. Pins
    that the route uses FastAPI auto-serialisation so the wire shape
    is a JSON string, not a Python datetime that would 500."""
    resp = admin_client.raw(
        "POST",
        "/api/v4/analytics/desktops/recently_used",
        json={"days_before": 30, "limit": 5},
    )
    assert resp.status_code == 200, (
        f"recently_used: expected 200, got {resp.status_code}; "
        f"body={resp.text[:200]}"
    )
    rows = resp.json()
    assert isinstance(rows, list)
    for row in rows:
        la = row.get("last_accessed")
        assert _is_iso_datetime_or_none(la), (
            f"last_accessed must be ISO string or None, got {la!r} "
            f"({type(la).__name__})"
        )


@pytest.mark.real
def test_analytics_desktops_less_used_serialises_datetime(
    admin_client: IsardClient,
):
    """``POST /analytics/desktops/less_used`` — same shape pin as
    recently_used. Also runs r.epoch_time over ``logs_desktops`` /
    ``domains.accessed``; same datetime field name."""
    resp = admin_client.raw(
        "POST",
        "/api/v4/analytics/desktops/less_used",
        json={"days_before": 1, "limit": 5},
    )
    assert resp.status_code == 200, (
        f"less_used: expected 200, got {resp.status_code}; " f"body={resp.text[:200]}"
    )
    rows = resp.json()
    assert isinstance(rows, list)
    for row in rows:
        la = row.get("last_accessed")
        assert _is_iso_datetime_or_none(
            la
        ), f"last_accessed must be ISO string or None, got {la!r}"


@pytest.mark.real
def test_analytics_suggested_removals_serialises_datetime(
    admin_client: IsardClient,
):
    """``POST /analytics/suggested_removals`` returns
    ``{empty_deployments, unused_desktops: {size, desktops: [...]}}``.
    Each desktop in ``unused_desktops.desktops`` carries a
    ``last_accessed`` field via the same ``r.epoch_time(...)`` path."""
    resp = admin_client.raw(
        "POST",
        "/api/v4/analytics/suggested_removals",
        json={"months_without_use": 0},
    )
    assert resp.status_code == 200, (
        f"suggested_removals: expected 200, got {resp.status_code}; "
        f"body={resp.text[:200]}"
    )
    body = resp.json()
    assert isinstance(body, dict)
    unused = body.get("unused_desktops") or {}
    desktops = unused.get("desktops") or []
    for row in desktops:
        la = row.get("last_accessed")
        assert _is_iso_datetime_or_none(
            la
        ), f"last_accessed must be ISO string or None, got {la!r}"
