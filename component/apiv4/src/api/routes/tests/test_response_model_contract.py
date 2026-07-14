#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""B3 contract — every FastAPI endpoint MUST declare ``response_model=``
unless it legitimately returns no body OR a raw non-JSON body.

Two ways an endpoint is exempt:

1. **No-content status code.** A route whose decorator sets
   ``status_code`` to 201/204 (and returns a raw ``Response``) has no
   response body by definition, so ``response_model=`` is meaningless.
   These are recognised automatically — this is the honest declaration
   for the many admin/user write endpoints that ``return
   Response(status_code=204)`` (and ``create_storage_pool`` at 201).

2. **200 response with a non-JSON body** (StreamingResponse /
   PlainTextResponse / FileResponse / raw image or CSV bytes). These
   still return 200, so they are NOT auto-exempt — they must be
   allowlisted explicitly in ``BUCKET_B_ALLOWLIST`` so a new endpoint
   silently dropping ``response_model=`` from a JSON handler fails CI
   rather than re-introducing 500-on-datetime serialisation regressions.

Removing ``response_model=`` from a handler that returns a 200 dict/list
is not acceptable — it must round-trip through FastAPI's
``jsonable_encoder``. The explicit allowlist must shrink, never grow.
"""

# HTTP status codes that carry no response body — an endpoint declaring
# one of these needs no ``response_model=``.
_NO_CONTENT_STATUS_CODES = frozenset({201, 204, 304})

from fastapi.routing import APIRoute

# (method, path) pairs whose handlers return a raw non-JSON body with a
# 200 status (StreamingResponse / PlainTextResponse / FileResponse / raw
# image or CSV bytes). No-content 201/204 routes are NOT listed here —
# they are recognised automatically via ``_NO_CONTENT_STATUS_CODES``.
# Verified against handler bodies on 2026-04-30.
BUCKET_B_ALLOWLIST: set[tuple[str, str]] = {
    # PlainTextResponse / raw image bytes
    ("GET", "/api/v4/item/category/{category_id}/custom_url"),
    ("GET", "/api/v4/logo"),
    ("GET", "/api/v4/logo/category/{category_id}"),
    ("GET", "/api/v4/logo-collapsed"),
    ("GET", "/api/v4/logo-collapsed/category/{category_id}"),
    # CSV / file download
    ("GET", "/api/v4/item/deployment/{deployment_id}/download-csv"),
    ("GET", "/api/v4/item/deployment/{deployment_id}/bastion/csv"),
    # StreamingResponse — VPN config bytes
    ("GET", "/api/v4/item/user/get-vpn"),
}


def _routes_without_response_model() -> list[tuple[str, str, str]]:
    from api import app

    offenders = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.response_model is not None:
            continue
        # Auto-exempt no-content routes (201/204): they carry no body,
        # so response_model= is meaningless.
        if getattr(route, "status_code", None) in _NO_CONTENT_STATUS_CODES:
            continue
        for method in route.methods:
            if method == "HEAD":
                continue
            if (method, route.path) in BUCKET_B_ALLOWLIST:
                continue
            offenders.append((method, route.path, route.endpoint.__name__))
    return sorted(offenders)


def test_every_route_declares_response_model():
    """B3 invariant: an endpoint lacking ``response_model=`` must either be
    decorated or added to ``BUCKET_B_ALLOWLIST`` in this file."""
    offenders = _routes_without_response_model()
    if offenders:
        listing = "\n  ".join(f"{m} {p} -> {n}" for m, p, n in offenders)
        raise AssertionError(
            "Endpoints without response_model= and not in "
            "BUCKET_B_ALLOWLIST. Either add response_model= to the "
            "route decorator, or — if the handler legitimately returns "
            "Response / StreamingResponse / PlainTextResponse / "
            "FileResponse — append the (method, path) tuple to "
            "BUCKET_B_ALLOWLIST in this test file.\n\n"
            f"Offenders:\n  {listing}"
        )


def test_bucket_b_allowlist_has_no_stale_entries():
    """Allowlist must shrink, never grow. A stale entry means a route was
    renamed or removed without the allowlist being updated."""
    from api import app

    real_routes = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if method != "HEAD"
    }
    stale = BUCKET_B_ALLOWLIST - real_routes
    assert not stale, (
        "BUCKET_B_ALLOWLIST has stale entries (route renamed or "
        f"removed): {sorted(stale)}"
    )
